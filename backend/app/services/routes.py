"""Reading routes (rutas): manual and automatic creation, plus the
recorrido (RouteRun) that walks a gestor through them meter by meter.

Shared by the admin and gestor routers so both build routes the same way."""

import datetime as dt
import math
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Gestor, Meter, Reading, Route, RouteRun, RouteRunStop, RouteStop
from app.schemas import RouteOut, RouteStopOut, RunOut, RunStopOut


# --- Routes ----------------------------------------------------------------


def get_route(db: Session, tenant_id: int, route_id: int) -> Route:
    route = db.query(Route).filter(Route.id == route_id, Route.tenant_id == tenant_id).first()
    if route is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ruta no encontrada")
    return route


def check_gestor(db: Session, tenant_id: int, gestor_id: int | None) -> None:
    if gestor_id is None:
        return
    exists = db.query(Gestor.id).filter(Gestor.id == gestor_id, Gestor.tenant_id == tenant_id).first()
    if exists is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gestor no encontrado")


def _validated_meters(db: Session, tenant_id: int, meter_ids: list[int]) -> list[Meter]:
    """Meters in the same order as `meter_ids`; rejects duplicates, unknown
    ids (or other tenants') and inactive meters."""
    if len(set(meter_ids)) != len(meter_ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Hay medidores repetidos en la ruta")
    meters = {
        m.id: m
        for m in db.query(Meter).filter(Meter.tenant_id == tenant_id, Meter.id.in_(meter_ids)).all()
    }
    missing = [i for i in meter_ids if i not in meters]
    if missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Medidor no encontrado: {missing[0]}")
    inactive = [m.codigo for m in meters.values() if not m.activo]
    if inactive:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Medidor inactivo: {inactive[0]}")
    return [meters[i] for i in meter_ids]


def set_stops(db: Session, route: Route, meter_ids: list[int]) -> None:
    meters = _validated_meters(db, route.tenant_id, meter_ids)
    route.stops.clear()
    db.flush()  # delete-orphan first, so the unique (route, meter) can't clash
    for orden, meter in enumerate(meters, start=1):
        route.stops.append(RouteStop(meter_id=meter.id, orden=orden))


def create_route(
    db: Session,
    tenant_id: int,
    nombre: str,
    meter_ids: list[int],
    gestor_id: int | None,
    origen: str = "manual",
) -> Route:
    check_gestor(db, tenant_id, gestor_id)
    route = Route(tenant_id=tenant_id, nombre=nombre, gestor_id=gestor_id, origen=origen)
    db.add(route)
    set_stops(db, route, meter_ids)
    db.commit()
    db.refresh(route)
    return route


def route_out(route: Route) -> RouteOut:
    return RouteOut(
        id=route.id,
        nombre=route.nombre,
        gestor_id=route.gestor_id,
        gestor_nombre=route.gestor.nombre if route.gestor else None,
        origen=route.origen,
        activo=route.activo,
        cantidad_medidores=len(route.stops),
        paradas=[
            RouteStopOut(
                meter_id=s.meter_id,
                orden=s.orden,
                codigo=s.meter.codigo,
                tipo=s.meter.tipo,
                direccion=s.meter.direccion,
                nombre_socio=s.meter.member.nombre,
            )
            for s in route.stops
        ],
    )


# --- Automatic generation --------------------------------------------------


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _nearest_neighbour_order(points: dict[int, tuple[float, float]]) -> list[int]:
    """Greedy walk: start at the westernmost meter and always hop to the
    closest unvisited one. Not optimal, but it yields compact, walkable
    stretches and chunking it gives geographically contiguous routes."""
    remaining = dict(points)
    current = min(remaining, key=lambda k: (remaining[k][1], remaining[k][0]))
    order = [current]
    pos = remaining.pop(current)
    while remaining:
        current = min(remaining, key=lambda k: _haversine_km(pos, remaining[k]))
        order.append(current)
        pos = remaining.pop(current)
    return order


def auto_generate(
    db: Session,
    tenant_id: int,
    *,
    tipo: str | None,
    meters_por_ruta: int,
    solo_pendientes: bool,
    gestor_id: int | None,
    nombre_base: str,
    preview: bool,
) -> list[RouteOut]:
    """Splits the active meters into routes of at most `meters_por_ruta`.

    Meters are ordered by proximity using the coordinates of their latest
    geolocated reading (gestores send lat/lon with each reading, so the map
    improves itself over time). Meters never read with a location go last,
    ordered by address."""
    check_gestor(db, tenant_id, gestor_id)

    query = db.query(Meter).filter(Meter.tenant_id == tenant_id, Meter.activo.is_(True))
    if tipo:
        query = query.filter(Meter.tipo == tipo)
    meters = query.all()

    if solo_pendientes:
        now = dt.datetime.utcnow()
        month_start = dt.datetime(now.year, now.month, 1)
        done = {
            r[0]
            for r in db.query(Reading.meter_id)
            .filter(Reading.tenant_id == tenant_id, Reading.created_at >= month_start)
            .distinct()
            .all()
        }
        meters = [m for m in meters if m.id not in done]

    if not meters:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No hay medidores para armar rutas")

    points: dict[int, tuple[float, float]] = {}
    for m in meters:
        last = (
            db.query(Reading)
            .filter(Reading.meter_id == m.id, Reading.lat.isnot(None), Reading.lon.isnot(None))
            .order_by(Reading.created_at.desc())
            .first()
        )
        if last:
            points[m.id] = (last.lat, last.lon)

    by_id = {m.id: m for m in meters}
    ordered = _nearest_neighbour_order(points) if points else []
    no_geo = sorted((m for m in meters if m.id not in points), key=lambda m: ((m.direccion or "").lower(), m.codigo))
    ordered += [m.id for m in no_geo]

    chunks = [ordered[i : i + meters_por_ruta] for i in range(0, len(ordered), meters_por_ruta)]
    gestor = db.get(Gestor, gestor_id) if gestor_id else None
    out = []
    for n, chunk in enumerate(chunks, start=1):
        nombre = f"{nombre_base} {n}"
        if preview:
            out.append(
                RouteOut(
                    id=None,
                    nombre=nombre,
                    gestor_id=gestor_id,
                    gestor_nombre=gestor.nombre if gestor else None,
                    origen="auto",
                    activo=True,
                    cantidad_medidores=len(chunk),
                    paradas=[
                        RouteStopOut(
                            meter_id=mid,
                            orden=i,
                            codigo=by_id[mid].codigo,
                            tipo=by_id[mid].tipo,
                            direccion=by_id[mid].direccion,
                            nombre_socio=by_id[mid].member.nombre,
                        )
                        for i, mid in enumerate(chunk, start=1)
                    ],
                )
            )
        else:
            out.append(route_out(create_route(db, tenant_id, nombre, chunk, gestor_id, origen="auto")))
    return out


# --- Recorridos (runs) -----------------------------------------------------


def get_run(db: Session, tenant_id: int, run_id: int) -> RouteRun:
    run = db.query(RouteRun).filter(RouteRun.id == run_id, RouteRun.tenant_id == tenant_id).first()
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recorrido no encontrado")
    return run


def active_run_for(db: Session, tenant_id: int, gestor_id: int, route_id: int | None = None) -> RouteRun | None:
    q = db.query(RouteRun).filter(
        RouteRun.tenant_id == tenant_id, RouteRun.gestor_id == gestor_id, RouteRun.status == "en_curso"
    )
    if route_id is not None:
        q = q.filter(RouteRun.route_id == route_id)
    return q.order_by(RouteRun.started_at.desc()).first()


def start_run(db: Session, route: Route, gestor: Gestor) -> RouteRun:
    """Starts (or resumes, if this gestor already has it open) a recorrido,
    snapshotting the route's currently active meters."""
    if not route.activo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La ruta está desactivada")
    if route.gestor_id not in (None, gestor.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "La ruta está asignada a otro gestor")

    existing = active_run_for(db, route.tenant_id, gestor.id, route.id)
    if existing:
        return existing

    stops = [s for s in route.stops if s.meter.activo]
    if not stops:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La ruta no tiene medidores activos")

    run = RouteRun(tenant_id=route.tenant_id, route_id=route.id, gestor_id=gestor.id)
    for orden, s in enumerate(stops, start=1):
        run.stops.append(RouteRunStop(meter_id=s.meter_id, orden=orden))
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def next_stop(run: RouteRun) -> RouteRunStop | None:
    return next((s for s in run.stops if s.status == "pendiente"), None)


def maybe_complete(db: Session, run: RouteRun) -> None:
    if run.status == "en_curso" and next_stop(run) is None:
        run.status = "completado"
        run.finished_at = dt.datetime.utcnow()
        db.add(run)
        db.commit()
        db.refresh(run)


def _stop_out(db: Session, stop: RouteRunStop) -> RunStopOut:
    m = stop.meter
    # Value as of when the gestor opens the stop: the latest reading that
    # isn't the one this very stop produced.
    q = db.query(Reading).filter(Reading.meter_id == m.id)
    if stop.reading_id:
        q = q.filter(Reading.id != stop.reading_id)
    last = q.order_by(Reading.created_at.desc()).first()
    return RunStopOut(
        id=stop.id,
        orden=stop.orden,
        status=stop.status,
        motivo=stop.motivo,
        meter_id=m.id,
        codigo=m.codigo,
        tipo=m.tipo,
        direccion=m.direccion,
        unidad=m.unidad,
        numero_socio=m.member.numero_socio,
        nombre_socio=m.member.nombre,
        ultima_lectura=last.valor if last else None,
        reading_id=stop.reading_id,
        completed_at=stop.completed_at,
    )


def run_out(db: Session, run: RouteRun, include_stops: bool = False) -> RunOut:
    nxt = next_stop(run)
    return RunOut(
        id=run.id,
        route_id=run.route_id,
        route_nombre=run.route.nombre,
        gestor_id=run.gestor_id,
        gestor_nombre=run.gestor.nombre,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        total=len(run.stops),
        leidas=sum(s.status == "leido" for s in run.stops),
        salteadas=sum(s.status == "salteado" for s in run.stops),
        pendientes=sum(s.status == "pendiente" for s in run.stops),
        siguiente=_stop_out(db, nxt) if nxt else None,
        paradas=[_stop_out(db, s) for s in run.stops] if include_stops else None,
    )
