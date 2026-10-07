"""Reading routes (rutas): manual and automatic creation, plus the
recorrido (RouteRun) that walks a gestor through them meter by meter.

Shared by the admin and gestor routers so both build routes the same way."""

import datetime as dt

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.models import Gestor, Meter, Reading, Route, RouteRun, RouteRunStop, RouteStop
from app.schemas import RouteOut, RouteStopOut, RunOut, RunStopOut
from app.services.readings import latest_readings_by_meter


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

# Two historical days count as "the same route" when at least this share of
# the smaller one's meters appears in the other (overlap coefficient).
SAME_ROUTE_OVERLAP = 0.6


def _split_sessions(readings: list[Reading], gap: dt.timedelta) -> list[list[Reading]]:
    """Splits one gestor's readings (sorted by time) into jornadas: a pause
    longer than `gap` closes the current one and the next reading opens a
    new one. The first/last reading of each jornada are the route's
    first/last meter."""
    sessions: list[list[Reading]] = []
    for r in readings:
        if sessions and r.created_at - sessions[-1][-1].created_at <= gap:
            sessions[-1].append(r)
        else:
            sessions.append([r])
    return sessions


def _session_meters(session: list[Reading]) -> list[int]:
    """Meter ids in the order first read; a meter corrected twice in the day
    counts once, at its first position."""
    seen: list[int] = []
    for r in session:
        if r.meter_id not in seen:
            seen.append(r.meter_id)
    return seen


def _same_route(a: list[int], b: list[int]) -> bool:
    return len(set(a) & set(b)) / min(len(a), len(b)) >= SAME_ROUTE_OVERLAP


def _consensus_order(sessions: list[list[int]]) -> list[int]:
    """Merges several runs of the same route (oldest -> newest) into one
    order. A meter is kept if it was in the latest run or in at least half
    of them (so a meter skipped once isn't lost, and a meter retired long
    ago doesn't linger). Position = average relative place within each run
    that included it; ties go to the most recent run."""
    latest = sessions[-1]
    positions: dict[int, list[float]] = {}
    for run in sessions:
        for i, mid in enumerate(run):
            positions.setdefault(mid, []).append(i / max(len(run) - 1, 1))
    keep = [mid for mid, p in positions.items() if mid in latest or len(p) * 2 >= len(sessions)]
    latest_idx = {mid: i for i, mid in enumerate(latest)}
    return sorted(keep, key=lambda m: (sum(positions[m]) / len(positions[m]), latest_idx.get(m, len(latest))))


def _route_preview(
    db: Session, meters: dict[int, Meter], nombre: str, ids: list[int], gestor: Gestor | None, base: int | None
) -> RouteOut:
    return RouteOut(
        id=None,
        nombre=nombre,
        gestor_id=gestor.id if gestor else None,
        gestor_nombre=gestor.nombre if gestor else None,
        origen="auto",
        activo=True,
        cantidad_medidores=len(ids),
        recorridos_base=base,
        paradas=[
            RouteStopOut(
                meter_id=mid,
                orden=i,
                codigo=meters[mid].codigo,
                tipo=meters[mid].tipo,
                direccion=meters[mid].direccion,
                nombre_socio=meters[mid].member.nombre,
            )
            for i, mid in enumerate(ids, start=1)
        ],
    )


def auto_generate(
    db: Session,
    tenant_id: int,
    *,
    tipo: str | None,
    gap_horas: float,
    min_medidores: int,
    meses_historial: int,
    incluir_sin_historial: bool,
    meters_por_ruta: int,
    solo_pendientes: bool,
    gestor_id: int | None,
    nombre_base: str,
    preview: bool,
) -> list[RouteOut]:
    """Infers routes from how the gestores actually worked, no location data
    needed.

    1. Each gestor's recent readings are cut into jornadas wherever there is
       a pause longer than `gap_horas` (first reading after the pause = first
       meter, last reading before the next pause = last meter).
    2. Jornadas with fewer than `min_medidores` meters are dropped (a few
       stray readings aren't a route).
    3. Jornadas covering mostly the same meters (e.g. the same route in
       different months) are merged into one with a consensus order.
    4. Active meters no jornada covers are grouped by address into routes of
       `meters_por_ruta` (if `incluir_sin_historial`)."""
    check_gestor(db, tenant_id, gestor_id)
    gestor = db.get(Gestor, gestor_id) if gestor_id else None

    query = db.query(Meter).filter(Meter.tenant_id == tenant_id, Meter.activo.is_(True))
    if tipo:
        query = query.filter(Meter.tipo == tipo)
    meters = {m.id: m for m in query.all()}

    now = dt.datetime.utcnow()
    month_start = dt.datetime(now.year, now.month, 1)
    done_this_month: set[int] = set()
    if solo_pendientes:
        done_this_month = {
            r[0]
            for r in db.query(Reading.meter_id)
            .filter(Reading.tenant_id == tenant_id, Reading.created_at >= month_start)
            .distinct()
            .all()
        }

    since = now - dt.timedelta(days=30 * meses_historial)
    history = (
        db.query(Reading)
        .filter(Reading.tenant_id == tenant_id, Reading.gestor_id.isnot(None), Reading.created_at >= since)
        .order_by(Reading.gestor_id, Reading.created_at)
        .all()
    )
    by_gestor: dict[int, list[Reading]] = {}
    for r in history:
        by_gestor.setdefault(r.gestor_id, []).append(r)

    jornadas: list[tuple[dt.datetime, list[int]]] = []  # (start, meter ids)
    for readings in by_gestor.values():
        for session in _split_sessions(readings, dt.timedelta(hours=gap_horas)):
            ids = [m for m in _session_meters(session) if m in meters]
            if len(ids) >= min_medidores:
                jornadas.append((session[0].created_at, ids))
    jornadas.sort(key=lambda j: j[0])

    # Cluster jornadas oldest -> newest; each joins the first cluster it matches.
    clusters: list[list[list[int]]] = []
    for _, ids in jornadas:
        for c in clusters:
            if _same_route(c[-1], ids):
                c.append(ids)
                break
        else:
            clusters.append([ids])

    candidates: list[tuple[list[int], int | None]] = []
    covered: set[int] = set()
    # Most-repeated routes first: they're the most trustworthy ones.
    for c in sorted(clusters, key=len, reverse=True):
        ids = [m for m in _consensus_order(c) if m not in covered and m not in done_this_month]
        if len(ids) >= min_medidores:
            candidates.append((ids, len(c)))
            covered.update(ids)
    covered.update(m for c in clusters for ids in c for m in ids)

    if incluir_sin_historial:
        rest = sorted(
            (m for m in meters.values() if m.id not in covered and m.id not in done_this_month),
            key=lambda m: ((m.direccion or "").lower(), m.codigo),
        )
        ids = [m.id for m in rest]
        candidates += [(ids[i : i + meters_por_ruta], None) for i in range(0, len(ids), meters_por_ruta)]

    if not candidates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No hay medidores ni historial suficiente para armar rutas")

    out = []
    for n, (ids, base) in enumerate(candidates, start=1):
        nombre = f"{nombre_base} {n}"
        if preview:
            out.append(_route_preview(db, meters, nombre, ids, gestor, base))
        else:
            route_out_ = route_out(create_route(db, tenant_id, nombre, ids, gestor_id, origen="auto"))
            route_out_.recorridos_base = base
            out.append(route_out_)
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


def _load_stops(db: Session, run: RouteRun) -> list[RouteRunStop]:
    """The run's stops with each meter and its member loaded in a single
    query, so building the response doesn't lazy-load them stop by stop."""
    return (
        db.query(RouteRunStop)
        .options(joinedload(RouteRunStop.meter).joinedload(Meter.member))
        .filter(RouteRunStop.run_id == run.id)
        .order_by(RouteRunStop.orden)
        .all()
    )


def _stops_out(db: Session, stops: list[RouteRunStop]) -> list[RunStopOut]:
    # Value as of when the gestor opens the stop: the latest reading that
    # isn't the one this very stop produced. A reading belongs to exactly one
    # meter (and a run has one stop per meter), so excluding every stop's own
    # reading at once is equivalent to excluding it per stop.
    last_by_meter = latest_readings_by_meter(
        db,
        [s.meter_id for s in stops],
        exclude_reading_ids=[s.reading_id for s in stops if s.reading_id],
    )
    own_ids = [s.reading_id for s in stops if s.reading_id]
    own = {r.id: r for r in db.query(Reading).filter(Reading.id.in_(own_ids)).all()} if own_ids else {}
    return [_stop_out(s, last_by_meter.get(s.meter_id), own.get(s.reading_id)) for s in stops]


def _stop_out(stop: RouteRunStop, last: Reading | None, own: Reading | None) -> RunStopOut:
    m = stop.meter
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
        ultima_lectura_fecha=last.created_at if last else None,
        ultima_lectura_id=last.id if last else None,
        reading_id=stop.reading_id,
        valor_leido=own.valor if own else None,
        completed_at=stop.completed_at,
    )


def run_out(db: Session, run: RouteRun, include_stops: bool = False) -> RunOut:
    nxt = next_stop(run)
    if include_stops:
        shown = _stops_out(db, _load_stops(db, run))
        next_out = next((o for o in shown if nxt and o.id == nxt.id), None)
    else:
        shown = None
        next_out = _stops_out(db, [nxt])[0] if nxt else None
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
        siguiente=next_out,
        paradas=shown,
    )
