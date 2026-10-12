"""Carga del padrón de medidores desde una planilla: una fila por medidor,
con el socio al que pertenece. Es lo que deja lista a una cooperativa para
usar la app de gestores con los números reales de medidor. Es opcional: la
importación mensual (services/importer.py) trae socios y facturas, y les
crea medidores con código provisorio (services/service_meters.py) que este
padrón, si se carga, reemplaza."""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import Member, Meter, Tenant
from app.services.importer import ImportError_, _clean_str, _parse_reading, _read_rows
from app.services.service_meters import (
    DEFAULT_UNIDAD,
    TIPOS,
    clear_sin_uso,
    ensure_service_meters,
    measured_services,
    provisional_code,
)

REQUIRED_COLUMNS = {"numero_socio", "nombre", "medidor"}


@dataclass
class MeterImportOutcome:
    rows_processed: int = 0
    meters_created: int = 0
    meters_updated: int = 0
    members_created: int = 0
    # One message per row that was left out, so the office can fix just
    # those and upload the file again.
    errors: list[str] = field(default_factory=list)


class RowError(Exception):
    pass


def _clean_code(value) -> str:
    """Códigos y números de socio suelen venir como número desde Excel:
    1001.0 tiene que quedar "1001", no "1001.0"."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return _clean_str(value)


def _clean_reading(value) -> float | None:
    try:
        return _parse_reading(value)
    except ValueError as exc:
        raise RowError(f"la lectura inicial {exc}")


def _clean_flag(value) -> bool:
    """Columna de sí/no: "si", "x", 1... Vacío es no."""
    if isinstance(value, bool):
        return value
    return _clean_code(value).lower() in {"si", "sí", "s", "x", "1", "true", "verdadero", "yes"}


def _clean_tipo(value) -> str | None:
    s = _clean_str(value).lower()
    if not s:
        return None
    if s not in TIPOS:
        raise RowError(f"el tipo «{s}» no es válido (usá luz, agua o gas)")
    return s


def upsert_meter(db: Session, tenant: Tenant, row: dict) -> tuple[Meter, bool, bool]:
    """Creates or updates one meter (and its socio, if new) from a row keyed
    like the planilla; returns it with whether the meter and the socio are
    new. A column that is absent or empty leaves the existing value alone,
    so re-uploading a partial file never blanks data out. A socio has one
    meter per servicio: if theirs still carries the provisional code it was
    auto-created with, the row gives it its real number instead of adding a
    second one. A second meter of the same servicio (another property) only
    goes in when the row says so with `adicional`. Doesn't commit. Raises RowError with the reason when the row
    can't be loaded."""
    numero_socio = _clean_code(row.get("numero_socio"))
    codigo = _clean_code(row.get("medidor"))
    if not numero_socio:
        raise RowError("falta el número de socio")
    if not codigo:
        raise RowError("falta el número de medidor")
    if len(numero_socio) > 64 or len(codigo) > 64:
        raise RowError("el número de socio y el de medidor admiten hasta 64 caracteres")

    nombre = _clean_str(row.get("nombre"))
    identificador = _clean_str(row.get("identificador"))
    tipo = _clean_tipo(row.get("tipo"))
    direccion = _clean_str(row.get("direccion"))
    unidad = _clean_str(row.get("unidad"))
    lectura_inicial = _clean_reading(row.get("lectura_inicial"))
    adicional = _clean_flag(row.get("adicional"))

    member = db.query(Member).filter(Member.tenant_id == tenant.id, Member.numero_socio == numero_socio).first()
    meter = db.query(Meter).filter(Meter.tenant_id == tenant.id, Meter.codigo == codigo).first()
    if meter is not None and (member is None or meter.member_id != member.id):
        raise RowError(
            f"el medidor {codigo} ya está cargado para el socio {meter.member.numero_socio} ({meter.member.nombre})"
        )

    member_created = member is None
    if member is None:
        if not nombre:
            raise RowError(f"el socio {numero_socio} no existe y falta su nombre para crearlo")
        member = Member(tenant_id=tenant.id, numero_socio=numero_socio, nombre=nombre, identificador=identificador)
        db.add(member)
        db.flush()
    else:
        if nombre:
            member.nombre = nombre
        if identificador:
            member.identificador = identificador

    if meter is None:
        # Sin columna de tipo, el medidor es del servicio de la cooperativa
        # (casi todas miden uno solo).
        servicios = measured_services(tenant)
        tipo = tipo or (servicios[0] if servicios else "luz")
        principal = (
            db.query(Meter)
            .filter(Meter.member_id == member.id, Meter.tipo == tipo, Meter.adicional.is_(False))
            .first()
        )
        if principal is None:
            # Nada que exceptuar: es el medidor del socio para ese servicio.
            adicional = False
        elif principal.codigo == provisional_code(member.numero_socio, tipo):
            # Tener número real es señal de que el servicio se usa: vuelve a
            # la app aunque se lo hubiera dado de baja por falta de uso.
            principal.codigo = codigo
            principal.activo = True
            clear_sin_uso(principal)
            meter = principal
        elif not adicional:
            raise RowError(
                f"el socio {numero_socio} ya tiene un medidor de {tipo} ({principal.codigo}); "
                "si este es de otra propiedad, cargalo como adicional"
            )

    meter_created = meter is None
    if meter is None:
        meter = Meter(
            tenant_id=tenant.id,
            member_id=member.id,
            codigo=codigo,
            tipo=tipo,
            direccion=direccion or None,
            unidad=unidad or DEFAULT_UNIDAD[tipo],
            lectura_inicial=lectura_inicial,
            adicional=adicional,
        )
        db.add(meter)
    else:
        if tipo and tipo != meter.tipo:
            taken = db.query(Meter.id).filter(
                Meter.member_id == member.id, Meter.tipo == tipo, Meter.adicional.is_(False)
            )
            if not meter.adicional and taken.first():
                raise RowError(f"el socio {numero_socio} ya tiene otro medidor de {tipo}")
            meter.tipo = tipo
        if direccion:
            meter.direccion = direccion
        if unidad:
            meter.unidad = unidad
        if lectura_inicial is not None:
            meter.lectura_inicial = lectura_inicial
    db.flush()
    ensure_service_meters(db, tenant, member)
    return meter, meter_created, member_created


def import_meters(db: Session, tenant: Tenant, filename: str, content: bytes) -> MeterImportOutcome:
    headers, rows = _read_rows(filename, content)

    missing = REQUIRED_COLUMNS - set(headers)
    if missing:
        raise ImportError_(f"Faltan columnas requeridas: {', '.join(sorted(missing))}")

    outcome = MeterImportOutcome()
    seen: set[str] = set()
    # Row 1 is the header, so data starts at 2 — the number the office sees
    # in the spreadsheet.
    for number, row in enumerate(rows, start=2):
        if all(not _clean_str(value) for value in row.values()):
            continue
        outcome.rows_processed += 1
        codigo = _clean_code(row.get("medidor"))
        try:
            if codigo and codigo in seen:
                raise RowError(f"el medidor {codigo} está repetido en la planilla")
            # A row that fails halfway (e.g. socio created, then a bad
            # lectura) must not leave its half behind.
            with db.begin_nested():
                _, meter_created, member_created = upsert_meter(db, tenant, row)
        except RowError as exc:
            outcome.errors.append(f"Fila {number}: {exc}")
            continue
        seen.add(codigo)
        outcome.meters_created += meter_created
        outcome.meters_updated += not meter_created
        outcome.members_created += member_created

    db.commit()
    return outcome
