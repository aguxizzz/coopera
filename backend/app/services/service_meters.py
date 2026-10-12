"""Regla "un medidor por servicio por socio": la cooperativa declara qué
servicios mide (Tenant.servicios_medidos) y cada socio tiene un medidor de
cada uno. Los que falten se crean solos, con un código provisorio, para que
un socio recién importado ya aparezca en la app de gestores sin esperar al
padrón (que es opcional: sólo hace falta para cargar los números reales)."""

import datetime as dt

from sqlalchemy.orm import Session

from app.models import Member, Meter, Tenant

TIPOS = ("luz", "agua", "gas")
DEFAULT_UNIDAD = {"luz": "kWh", "agua": "m3", "gas": "m3"}

# Motivo con el que el gestor saltea una parada cuando el socio no tiene ese
# servicio. Es el mismo texto que manda la app (mobile/src/lib/runActions.ts):
# viaja como motivo común para que también funcione desde la cola sin señal.
MOTIVO_NO_USA_SERVICIO = "El socio no usa este servicio"


def measured_services(tenant: Tenant) -> list[str]:
    return [t for t in (tenant.servicios_medidos or []) if t in TIPOS]


def is_sin_uso(motivo: str | None) -> bool:
    return (motivo or "").strip().lower() == MOTIVO_NO_USA_SERVICIO.lower()


def report_sin_uso(meter: Meter, gestor_id: int | None) -> None:
    """Deja el medidor a confirmar por la oficina; no lo da de baja. Doesn't
    commit."""
    meter.sin_uso_reportado_at = dt.datetime.utcnow()
    meter.sin_uso_reportado_por_id = gestor_id


def clear_sin_uso(meter: Meter) -> None:
    meter.sin_uso_reportado_at = None
    meter.sin_uso_reportado_por_id = None


def provisional_code(numero_socio: str, tipo: str) -> str:
    """Código de un medidor creado automáticamente (ej. "1001-luz"). El
    padrón lo reemplaza por el número real cuando se carga."""
    return f"{numero_socio}-{tipo}"


def ensure_service_meters(db: Session, tenant: Tenant, member: Member) -> int:
    """Creates the meters `member` is missing for the services the
    cooperativa measures; returns how many it created. Idempotent, and
    doesn't commit."""
    servicios = measured_services(tenant)
    if not servicios:
        return 0

    existentes = {tipo for (tipo,) in db.query(Meter.tipo).filter(Meter.member_id == member.id)}
    created = 0
    for tipo in servicios:
        if tipo in existentes:
            continue
        codigo = provisional_code(member.numero_socio, tipo)
        # El código es único por cooperativa: si justo coincide con el de
        # otro medidor (o no entra en la columna), ese socio queda para
        # cargarse por el padrón en vez de frenar toda la importación.
        if len(codigo) > 64:
            continue
        if db.query(Meter.id).filter(Meter.tenant_id == tenant.id, Meter.codigo == codigo).first():
            continue
        db.add(
            Meter(
                tenant_id=tenant.id,
                member_id=member.id,
                codigo=codigo,
                tipo=tipo,
                unidad=DEFAULT_UNIDAD[tipo],
            )
        )
        created += 1
    if created:
        db.flush()
    return created


def ensure_all_service_meters(db: Session, tenant: Tenant) -> int:
    """Backfill for every socio of the cooperativa, e.g. right after its
    measured services change. Doesn't commit."""
    members = db.query(Member).filter(Member.tenant_id == tenant.id).all()
    return sum(ensure_service_meters(db, tenant, member) for member in members)
