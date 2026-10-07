"""Consumption-anomaly heuristic used when a gestor (or an admin, manually)
registers a new meter reading. Kept deliberately simple: it only has to
catch the two mistakes that actually happen in the field (misread digit,
or skipped meter) so a human reviews before the reading feeds a bill."""

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.models import Meter, Reading

# A jump bigger than this multiple of the meter's recent average consumption
# gets flagged for review. 4x comfortably allows for seasonal swings (e.g.
# an electric heater turned on) while still catching a misread digit, which
# routinely blows past 10x.
ANOMALY_MULTIPLIER = 4
HISTORY_SIZE = 6


def latest_readings_by_meter(
    db: Session,
    meter_ids: Iterable[int] | Select,
    exclude_reading_ids: Iterable[int] = (),
) -> dict[int, Reading]:
    """Most recent reading of each given meter, in ONE query (a window
    function ranks every meter's readings newest-first and keeps rank 1),
    instead of one query per meter. `meter_ids` may be a list or a
    `select(Meter.id)...`. Readings in `exclude_reading_ids` are skipped, as
    when a stop wants the value *before* the reading it produced itself."""
    if not isinstance(meter_ids, Select):
        meter_ids = list(meter_ids)
        if not meter_ids:
            return {}
    excluded = list(exclude_reading_ids)

    ranked = select(
        Reading.id.label("id"),
        func.row_number()
        .over(partition_by=Reading.meter_id, order_by=(Reading.created_at.desc(), Reading.id.desc()))
        .label("rn"),
    ).where(Reading.meter_id.in_(meter_ids))
    if excluded:
        ranked = ranked.where(Reading.id.notin_(excluded))
    ranked = ranked.subquery()

    rows = db.query(Reading).join(ranked, Reading.id == ranked.c.id).filter(ranked.c.rn == 1).all()
    return {r.meter_id: r for r in rows}


def register_reading(
    db: Session,
    meter: Meter,
    valor: float,
    gestor_id: int | None = None,
    foto_urls: list[str] | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> Reading:
    history = (
        db.query(Reading)
        .filter(Reading.meter_id == meter.id)
        .order_by(Reading.created_at.desc())
        .limit(HISTORY_SIZE)
        .all()
    )

    valor_anterior = history[0].valor if history else None
    consumo = (valor - valor_anterior) if valor_anterior is not None else None
    anomala = _is_anomalous(consumo, history)

    reading = Reading(
        tenant_id=meter.tenant_id,
        meter_id=meter.id,
        gestor_id=gestor_id,
        valor=valor,
        valor_anterior=valor_anterior,
        consumo=consumo,
        foto_urls=foto_urls,
        lat=lat,
        lon=lon,
        anomala=anomala,
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


def update_reading(
    db: Session,
    reading: Reading,
    valor: float,
    foto_urls: list[str] | None = None,
) -> Reading:
    """Corrects a reading the gestor already submitted this same cycle
    (e.g. a misread digit caught right after saving), recomputing consumo/
    anomala exactly like register_reading would — but against the history
    excluding this reading itself, since editing it shouldn't let it count
    as its own previous value."""
    history = (
        db.query(Reading)
        .filter(Reading.meter_id == reading.meter_id, Reading.id != reading.id)
        .order_by(Reading.created_at.desc())
        .limit(HISTORY_SIZE)
        .all()
    )

    valor_anterior = history[0].valor if history else None
    consumo = (valor - valor_anterior) if valor_anterior is not None else None
    anomala = _is_anomalous(consumo, history)

    reading.valor = valor
    reading.valor_anterior = valor_anterior
    reading.consumo = consumo
    reading.anomala = anomala
    if foto_urls is not None:
        reading.foto_urls = foto_urls

    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


def _is_anomalous(consumo: float | None, history: list[Reading]) -> bool:
    if consumo is None:
        return False  # no hay lectura previa: no hay base de comparación
    if consumo < 0:
        return True  # el medidor nunca retrocede

    past_deltas = [h.consumo for h in history if h.consumo is not None and h.consumo >= 0]
    if len(past_deltas) < 2:
        return False  # todavía no hay suficiente historial para un promedio confiable

    avg_delta = sum(past_deltas) / len(past_deltas)
    if avg_delta <= 0:
        return False
    return consumo > ANOMALY_MULTIPLIER * avg_delta
