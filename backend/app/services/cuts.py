"""Cortes de servicio: ordenar (admin), ejecutar y reponer (gestor).

Un corte está "vigente" mientras su estado sea ordenado, ejecutado o
reposicion_ordenada. Un medidor tiene como máximo uno vigente, y mientras lo
tenga queda fuera de los recorridos de lectura."""

import datetime as dt

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.models import Member, Meter, RouteRun, RouteRunStop, ServiceCut
from app.schemas import ServiceCutOut

ACTIVE_STATES = ("ordenado", "ejecutado", "reposicion_ordenada")
# De más a menos avanzado, para resumir varios cortes de un mismo socio.
_STATE_PRIORITY = ("ejecutado", "reposicion_ordenada", "ordenado")

SKIP_MOTIVO = "Corte ordenado"


def active_cuts_by_meter(db: Session, tenant_id: int) -> dict[int, ServiceCut]:
    cuts = (
        db.query(ServiceCut)
        .filter(ServiceCut.tenant_id == tenant_id, ServiceCut.estado.in_(ACTIVE_STATES))
        .all()
    )
    return {c.meter_id: c for c in cuts}


def cut_state_by_member(db: Session, tenant_id: int) -> dict[int, str]:
    by_member: dict[int, set[str]] = {}
    for c in active_cuts_by_meter(db, tenant_id).values():
        by_member.setdefault(c.member_id, set()).add(c.estado)
    return {
        member_id: next(s for s in _STATE_PRIORITY if s in states)
        for member_id, states in by_member.items()
    }


def list_cuts(db: Session, tenant_id: int, estados: tuple[str, ...] | None = None) -> list[ServiceCut]:
    query = (
        db.query(ServiceCut)
        .options(
            joinedload(ServiceCut.meter),
            joinedload(ServiceCut.member),
            joinedload(ServiceCut.ejecutado_por),
            joinedload(ServiceCut.repuesto_por),
        )
        .filter(ServiceCut.tenant_id == tenant_id)
    )
    if estados:
        query = query.filter(ServiceCut.estado.in_(estados))
    return query.order_by(ServiceCut.created_at.desc(), ServiceCut.id.desc()).all()


def get_cut(db: Session, tenant_id: int, cut_id: int) -> ServiceCut:
    cut = db.query(ServiceCut).filter(ServiceCut.id == cut_id, ServiceCut.tenant_id == tenant_id).first()
    if cut is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Corte no encontrado")
    return cut


def cut_out(cut: ServiceCut) -> ServiceCutOut:
    return ServiceCutOut(
        id=cut.id,
        meter_id=cut.meter_id,
        codigo=cut.meter.codigo,
        tipo=cut.meter.tipo,
        direccion=cut.meter.direccion,
        member_id=cut.member_id,
        numero_socio=cut.member.numero_socio,
        nombre_socio=cut.member.nombre,
        motivo=cut.motivo,
        detalle=cut.detalle,
        estado=cut.estado,
        ordenado_por_email=cut.ordenado_por_email,
        created_at=cut.created_at,
        ejecutado_por_nombre=cut.ejecutado_por.nombre if cut.ejecutado_por else None,
        ejecutado_at=cut.ejecutado_at,
        ejecucion_nota=cut.ejecucion_nota,
        ejecucion_foto_urls=cut.ejecucion_foto_urls,
        reposicion_ordenada_por_email=cut.reposicion_ordenada_por_email,
        reposicion_ordenada_at=cut.reposicion_ordenada_at,
        repuesto_por_nombre=cut.repuesto_por.nombre if cut.repuesto_por else None,
        repuesto_at=cut.repuesto_at,
        reposicion_nota=cut.reposicion_nota,
        reposicion_foto_urls=cut.reposicion_foto_urls,
        cancelado_por_email=cut.cancelado_por_email,
        cancelado_at=cut.cancelado_at,
    )


def order_cuts(
    db: Session,
    member: Member,
    meter_ids: list[int] | None,
    motivo: str,
    detalle: str | None,
    admin_email: str,
) -> list[ServiceCut]:
    """Orders one cut per meter. With `meter_ids=None` it covers every active
    meter of the member that doesn't already have a cut in force."""
    in_force = active_cuts_by_meter(db, member.tenant_id)
    own = db.query(Meter).filter(Meter.member_id == member.id, Meter.tenant_id == member.tenant_id).all()

    if meter_ids is None:
        meters = [m for m in own if m.activo and m.id not in in_force]
        if not meters:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El socio no tiene medidores para cortar")
    else:
        if len(set(meter_ids)) != len(meter_ids):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Hay medidores repetidos")
        by_id = {m.id: m for m in own}
        missing = [i for i in meter_ids if i not in by_id]
        if missing:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Medidor no encontrado: {missing[0]}")
        meters = [by_id[i] for i in meter_ids]
        busy = [m.codigo for m in meters if m.id in in_force]
        if busy:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El medidor {busy[0]} ya tiene un corte vigente")

    cuts = [
        ServiceCut(
            tenant_id=member.tenant_id,
            member_id=member.id,
            meter_id=m.id,
            motivo=motivo,
            detalle=detalle,
            ordenado_por_email=admin_email,
        )
        for m in meters
    ]
    db.add_all(cuts)
    _skip_pending_stops(db, [m.id for m in meters])
    db.commit()
    for c in cuts:
        db.refresh(c)
    return cuts


def _skip_pending_stops(db: Session, meter_ids: list[int]) -> None:
    """Meters just ordered cut drop out of recorridos already in progress:
    their pending stops are skipped, and a recorrido left with nothing
    pending is completed."""
    from app.services.routes import maybe_complete

    stops = (
        db.query(RouteRunStop)
        .join(RouteRun, RouteRun.id == RouteRunStop.run_id)
        .filter(
            RouteRun.status == "en_curso",
            RouteRunStop.meter_id.in_(meter_ids),
            RouteRunStop.status == "pendiente",
        )
        .all()
    )
    now = dt.datetime.utcnow()
    for s in stops:
        s.status = "salteado"
        s.motivo = SKIP_MOTIVO
        s.completed_at = now
    db.flush()
    for run in {s.run for s in stops}:
        db.refresh(run)
        maybe_complete(db, run)


def cancel(db: Session, cut: ServiceCut, admin_email: str) -> ServiceCut:
    """Cancels an order not yet carried out (ordenado), or withdraws a
    reposition order (reposicion_ordenada -> back to ejecutado)."""
    if cut.estado == "ordenado":
        cut.estado = "cancelado"
        cut.cancelado_por_email = admin_email
        cut.cancelado_at = dt.datetime.utcnow()
    elif cut.estado == "reposicion_ordenada":
        cut.estado = "ejecutado"
        cut.reposicion_ordenada_por_email = None
        cut.reposicion_ordenada_at = None
    else:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este corte ya no se puede cancelar")
    db.commit()
    db.refresh(cut)
    return cut


def order_restore(db: Session, cut: ServiceCut, admin_email: str) -> ServiceCut:
    if cut.estado != "ejecutado":
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo se puede reponer un servicio ya cortado")
    cut.estado = "reposicion_ordenada"
    cut.reposicion_ordenada_por_email = admin_email
    cut.reposicion_ordenada_at = dt.datetime.utcnow()
    db.commit()
    db.refresh(cut)
    return cut


def execute(
    db: Session,
    cut: ServiceCut,
    gestor_id: int,
    nota: str | None,
    foto_urls: list[str] | None,
    lat: float | None,
    lon: float | None,
) -> ServiceCut:
    if cut.estado != "ordenado":
        raise HTTPException(status.HTTP_409_CONFLICT, "Este corte no está pendiente de ejecución")
    cut.estado = "ejecutado"
    cut.ejecutado_por_id = gestor_id
    cut.ejecutado_at = dt.datetime.utcnow()
    cut.ejecucion_nota = nota
    cut.ejecucion_foto_urls = foto_urls
    cut.ejecucion_lat = lat
    cut.ejecucion_lon = lon
    db.commit()
    db.refresh(cut)
    return cut


def restore(
    db: Session,
    cut: ServiceCut,
    gestor_id: int,
    nota: str | None,
    foto_urls: list[str] | None,
    lat: float | None,
    lon: float | None,
) -> ServiceCut:
    if cut.estado != "reposicion_ordenada":
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta reposición no está pendiente")
    cut.estado = "repuesto"
    cut.repuesto_por_id = gestor_id
    cut.repuesto_at = dt.datetime.utcnow()
    cut.reposicion_nota = nota
    cut.reposicion_foto_urls = foto_urls
    cut.reposicion_lat = lat
    cut.reposicion_lon = lon
    db.commit()
    db.refresh(cut)
    return cut
