"""Planilla con las lecturas de un mes, para que una cooperativa que factura
en su propio sistema se lleve lo que cargaron los gestores sin depender del
portal de socios."""

import csv
import datetime as dt
import io
from dataclasses import dataclass

from openpyxl import Workbook
from sqlalchemy.orm import Session, joinedload

from app.models import Meter, Reading, Tenant
from app.services.readings import latest_readings_by_meter

# `created_at` se guarda en UTC; la planilla muestra la hora de Argentina
# (UTC-3 fijo, sin horario de verano).
ARGENTINA = dt.timezone(dt.timedelta(hours=-3))

HEADERS = [
    "numero_socio",
    "nombre",
    "medidor",
    "tipo",
    "direccion",
    "lectura_anterior",
    "lectura_actual",
    "consumo",
    "unidad",
    "fecha",
    "gestor",
    "inusual",
    "observacion",
]


@dataclass
class ExportRow:
    """One meter in the month's planilla. `reading` is None when nobody read
    it that month: the row still goes out, with the reading left empty, so
    the office sees what is missing instead of billing off a short file."""

    meter: Meter
    reading: Reading | None
    lectura_anterior: float | None


def _period(year: int, month: int) -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime(year, month, 1)
    end = dt.datetime(year + 1, 1, 1) if month == 12 else dt.datetime(year, month + 1, 1)
    return start, end


def period_rows(db: Session, tenant: Tenant, year: int, month: int) -> list[ExportRow]:
    """Every meter the month should have a reading for, ordered by socio and
    meter. A read meter carries the reading it is billed off: its latest one
    of the month. The month runs on UTC like the rest of the cycle logic (see
    routers/gestor.py's _in_current_cycle), so the export matches the "one
    reading per month" the app enforces.

    Unread meters are the active ones that already existed that month; one
    read and deactivated afterwards keeps its row."""
    start, end = _period(year, month)
    readings = (
        db.query(Reading)
        .options(joinedload(Reading.meter).joinedload(Meter.member), joinedload(Reading.gestor))
        .filter(Reading.tenant_id == tenant.id, Reading.created_at >= start, Reading.created_at < end)
        .order_by(Reading.created_at.desc(), Reading.id.desc())
        .all()
    )
    latest: dict[int, Reading] = {}
    for reading in readings:
        latest.setdefault(reading.meter_id, reading)
    rows = [ExportRow(r.meter, r, r.valor_anterior) for r in latest.values()]

    unread = (
        db.query(Meter)
        .options(joinedload(Meter.member))
        .filter(Meter.tenant_id == tenant.id, Meter.activo.is_(True), Meter.created_at < end)
        .all()
    )
    unread = [m for m in unread if m.id not in latest]
    previous = latest_readings_by_meter(db, [m.id for m in unread], before=start)
    for meter in unread:
        last = previous.get(meter.id)
        rows.append(ExportRow(meter, None, last.valor if last else meter.lectura_inicial))

    return sorted(rows, key=lambda row: (row.meter.member.numero_socio, row.meter.codigo))


def _row(row: ExportRow) -> list:
    meter, reading = row.meter, row.reading
    values = [
        meter.member.numero_socio,
        meter.member.nombre,
        meter.codigo,
        meter.tipo,
        meter.direccion or "",
        row.lectura_anterior,
    ]
    if reading is None:
        aviso = "Gestor informó: el socio no usa este servicio" if meter.sin_uso_reportado_at else ""
        return values + [None, None, meter.unidad, "", "", "", aviso]
    fecha = reading.created_at.replace(tzinfo=dt.timezone.utc).astimezone(ARGENTINA)
    return values + [
        reading.valor,
        reading.consumo,
        meter.unidad,
        fecha.strftime("%Y-%m-%d %H:%M"),
        reading.gestor.nombre if reading.gestor else "",
        "si" if reading.anomala else "no",
        reading.observacion or "",
    ]


def build_csv(rows: list[ExportRow]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(HEADERS)
    for row in rows:
        writer.writerow(["" if value is None else value for value in _row(row)])
    # BOM so Excel reads the accents right when someone opens the .csv directly.
    return buffer.getvalue().encode("utf-8-sig")


def build_xlsx(rows: list[ExportRow]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Lecturas"
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(_row(row))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
