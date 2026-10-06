from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.auth import (
    consume_gestor_refresh_token,
    create_device_token,
    create_gestor_access_token,
    decode_device_token,
    get_current_gestor,
    issue_gestor_refresh_token,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.deps import get_tenant
from app.models import Gestor, Meter, Reading, Route, RouteRunStop
from app.rate_limit import limiter
from app.schemas import (
    GestorDeviceLogin,
    GestorDeviceLoginResponse,
    GestorProfileOut,
    GestorQrClaimOut,
    GestorQrPollOut,
    GestorRefreshRequest,
    GestorSelectProfile,
    GestorTokenResponse,
    MeterOut,
    ReadingOut,
    RouteAutoGenerate,
    RouteCreate,
    RouteOut,
    RunOut,
    RunSkip,
    RunStopResult,
)
from app.services.audit import log_action
from app.services.qr_login import claim as claim_qr_session, get_qr_session, resolve_status
from app.services import routes as route_service
from app.services.readings import register_reading, update_reading
from app.services.storage import UnsupportedPhotoType, upload_reading_photo

import datetime as dt

_UPLOAD_CHUNK_SIZE = 1024 * 1024

# Evidence photos only (no OCR) — a gestor rarely needs more than a couple
# angles of a dial-style meter, and capping it keeps the multipart upload
# bounded on the spotty connections these are taken over.
MAX_READING_PHOTOS = 3


async def _read_capped(upload: UploadFile, max_bytes: int) -> bytes:
    """Reads an UploadFile in chunks, bailing out as soon as it exceeds
    max_bytes instead of buffering an unbounded body into memory first."""
    chunks = []
    total = 0
    while True:
        chunk = await upload.read(_UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"La foto supera el tamaño máximo permitido ({max_bytes // (1024 * 1024)} MB)",
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def _upload_reading_photos(tenant_slug: str, fotos: list[UploadFile]) -> list[str]:
    if len(fotos) > MAX_READING_PHOTOS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Se permiten hasta {MAX_READING_PHOTOS} fotos por lectura"
        )
    urls = []
    for foto in fotos:
        content = await _read_capped(foto, settings.max_reading_photo_bytes)
        try:
            urls.append(
                upload_reading_photo(tenant_slug, foto.filename or "lectura.jpg", foto.content_type or "", content)
            )
        except UnsupportedPhotoType as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return urls


router = APIRouter(prefix="/api/t/{tenant_slug}/gestor", tags=["gestor"])


@router.post("/device-login", response_model=GestorDeviceLoginResponse)
@limiter.limit("5/minute")
def device_login(
    request: Request, tenant_slug: str, payload: GestorDeviceLogin, db: Session = Depends(get_db)
):
    """First step of the shared "household" login: the device proves it
    knows the cooperativa's single gestor password and gets back a
    short-lived device token plus the list of active gestor profiles to
    choose from. Mirrors Netflix's one-login-many-profiles flow instead of
    giving every gestor their own credentials."""
    tenant = get_tenant(tenant_slug, db)
    if tenant.gestor_shared_password_hash is None or not verify_password(
        payload.password, tenant.gestor_shared_password_hash
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Contraseña inválida")

    profiles = (
        db.query(Gestor)
        .filter(Gestor.tenant_id == tenant.id, Gestor.activo.is_(True))
        .order_by(Gestor.nombre)
        .all()
    )
    device_token = create_device_token(tenant.id)
    return GestorDeviceLoginResponse(
        device_token=device_token,
        profiles=[GestorProfileOut(id=g.id, nombre=g.nombre) for g in profiles],
    )


@router.post("/select-profile", response_model=GestorTokenResponse)
@limiter.limit("20/minute")
def select_profile(
    request: Request, tenant_slug: str, payload: GestorSelectProfile, db: Session = Depends(get_db)
):
    """Second step: the device picks which gestor is reading today. This is
    what gets recorded as the audit trail for "who did this" even though
    the login itself is shared — every token minted here (and every Reading
    it later creates) is tied to this specific gestor_id."""
    tenant = get_tenant(tenant_slug, db)
    decode_device_token(tenant.id, payload.device_token)

    gestor = (
        db.query(Gestor)
        .filter(Gestor.id == payload.gestor_id, Gestor.tenant_id == tenant.id)
        .first()
    )
    if gestor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gestor no encontrado")
    if not gestor.activo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Gestor inactivo")

    token = create_gestor_access_token(gestor.id, tenant.id)
    refresh_token = issue_gestor_refresh_token(db, gestor)
    log_action(
        db,
        tenant,
        gestor,
        "gestor.profile_selected",
        target=f"gestor:{gestor.id}",
        actor_type="gestor",
    )
    return GestorTokenResponse(access_token=token, refresh_token=refresh_token)


@router.post("/qr-session/{code}/claim", response_model=GestorQrClaimOut)
@limiter.limit("20/minute")
def claim_qr(request: Request, tenant_slug: str, code: str, db: Session = Depends(get_db)):
    """Called by the gestor app right after it scans the admin panel's QR.
    Doesn't hand back anything sensitive — it only flags the code as
    "claimed" so the admin sees a confirm/deny prompt. See
    app/services/qr_login.py for why that human approval step matters."""
    tenant = get_tenant(tenant_slug, db)
    session = get_qr_session(db, tenant.id, code)
    return GestorQrClaimOut(status=claim_qr_session(db, session))


@router.get("/qr-session/{code}", response_model=GestorQrPollOut)
@limiter.limit("120/minute")
def poll_qr(request: Request, tenant_slug: str, code: str, db: Session = Depends(get_db)):
    """Polled by the gestor app while it waits for an admin to approve the
    scan. Returns device_token + profiles exactly once (the same shape
    /device-login returns), right after an admin approves — a second poll
    after that gets "expired" instead of being able to replay the token."""
    tenant = get_tenant(tenant_slug, db)
    session = get_qr_session(db, tenant.id, code)
    status_now = resolve_status(db, session)

    if status_now == "approved" and not session.consumed:
        session.consumed = True
        db.add(session)
        db.commit()
        profiles = (
            db.query(Gestor)
            .filter(Gestor.tenant_id == tenant.id, Gestor.activo.is_(True))
            .order_by(Gestor.nombre)
            .all()
        )
        return GestorQrPollOut(
            status="approved",
            device_token=session.device_token,
            profiles=[GestorProfileOut(id=g.id, nombre=g.nombre) for g in profiles],
        )
    if status_now == "approved":  # already consumed by an earlier poll
        return GestorQrPollOut(status="expired")
    return GestorQrPollOut(status=status_now)


@router.post("/refresh", response_model=GestorTokenResponse)
@limiter.limit("20/minute")
def refresh(
    request: Request, tenant_slug: str, payload: GestorRefreshRequest, db: Session = Depends(get_db)
):
    """Silently mints a new access token (and rotates the refresh token) so
    the mobile app never has to force a logout just because the 1h access
    token expired mid-route — see mobile/src/lib/api.ts."""
    tenant = get_tenant(tenant_slug, db)
    gestor = consume_gestor_refresh_token(db, tenant.id, payload.refresh_token)
    token = create_gestor_access_token(gestor.id, tenant.id)
    refresh_token = issue_gestor_refresh_token(db, gestor)
    return GestorTokenResponse(access_token=token, refresh_token=refresh_token)


@router.get("/meters", response_model=list[MeterOut])
def list_meters(
    tenant_slug: str,
    db: Session = Depends(get_db),
    gestor: Gestor = Depends(get_current_gestor),
):
    """Every active meter for the cooperativa. There's no per-gestor route
    assignment yet; every gestor sees the whole town, same as the paper
    books they're replacing."""
    tenant = get_tenant(tenant_slug, db)
    meters = (
        db.query(Meter)
        .filter(Meter.tenant_id == tenant.id, Meter.activo.is_(True))
        .order_by(Meter.codigo)
        .all()
    )

    rows = []
    for meter in meters:
        last = (
            db.query(Reading)
            .filter(Reading.meter_id == meter.id)
            .order_by(Reading.created_at.desc())
            .first()
        )
        rows.append(
            MeterOut(
                id=meter.id,
                codigo=meter.codigo,
                tipo=meter.tipo,
                direccion=meter.direccion,
                unidad=meter.unidad,
                activo=meter.activo,
                member_id=meter.member_id,
                numero_socio=meter.member.numero_socio,
                nombre_socio=meter.member.nombre,
                ultima_lectura=last.valor if last else None,
                ultima_lectura_fecha=last.created_at if last else None,
                ultima_lectura_anomala=last.anomala if last else False,
                ultima_lectura_id=last.id if last else None,
            )
        )
    return rows


def _get_meter(db: Session, tenant_id: int, meter_id: int) -> Meter:
    meter = db.query(Meter).filter(Meter.id == meter_id, Meter.tenant_id == tenant_id).first()
    if meter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Medidor no encontrado")
    return meter


@router.post("/meters/{meter_id}/readings", response_model=ReadingOut)
async def create_reading(
    tenant_slug: str,
    meter_id: int,
    valor: float = Form(...),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    foto: list[UploadFile] | None = File(None),
    db: Session = Depends(get_db),
    gestor: Gestor = Depends(get_current_gestor),
):
    tenant = get_tenant(tenant_slug, db)
    meter = _get_meter(db, tenant.id, meter_id)

    foto_urls = await _upload_reading_photos(tenant.slug, foto or [])

    reading = register_reading(
        db,
        meter,
        valor,
        gestor_id=gestor.id,
        foto_urls=foto_urls or None,
        lat=lat,
        lon=lon,
    )
    return reading


@router.get("/meters/{meter_id}/readings", response_model=list[ReadingOut])
def list_meter_readings(
    tenant_slug: str,
    meter_id: int,
    db: Session = Depends(get_db),
    gestor: Gestor = Depends(get_current_gestor),
):
    tenant = get_tenant(tenant_slug, db)
    meter = _get_meter(db, tenant.id, meter_id)
    return (
        db.query(Reading)
        .filter(Reading.meter_id == meter.id)
        .order_by(Reading.created_at.desc())
        .all()
    )


def _get_reading(db: Session, meter_id: int, reading_id: int) -> Reading:
    reading = (
        db.query(Reading)
        .filter(Reading.id == reading_id, Reading.meter_id == meter_id)
        .first()
    )
    if reading is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lectura no encontrada")
    return reading


@router.patch("/meters/{meter_id}/readings/{reading_id}", response_model=ReadingOut)
async def update_reading_endpoint(
    tenant_slug: str,
    meter_id: int,
    reading_id: int,
    valor: float = Form(...),
    foto: list[UploadFile] | None = File(None),
    db: Session = Depends(get_db),
    gestor: Gestor = Depends(get_current_gestor),
):
    """Corrects a reading the gestor already loaded, instead of stacking a
    second one — services are billed off a single monthly reading, so
    letting a misread-digit fix pile up a duplicate instead of overwriting
    the original would double-count the cycle. Only readings still inside
    the current calendar month (i.e. not yet closed for billing) can be
    touched this way; anything older needs an admin correction."""
    tenant = get_tenant(tenant_slug, db)
    meter = _get_meter(db, tenant.id, meter_id)
    reading = _get_reading(db, meter.id, reading_id)

    now = dt.datetime.utcnow()
    if reading.created_at.year != now.year or reading.created_at.month != now.month:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Esta lectura ya no pertenece al ciclo actual y no se puede editar desde la app",
        )

    foto_urls = await _upload_reading_photos(tenant.slug, foto or [])

    reading = update_reading(
        db,
        reading,
        valor,
        foto_urls=foto_urls or None,
    )
    log_action(
        db, tenant, gestor, "gestor.reading_updated", target=f"reading:{reading.id}", actor_type="gestor"
    )
    return reading


# --- Rutas y recorridos ------------------------------------------------------


def _visible_routes(db: Session, tenant_id: int, gestor: Gestor) -> list[Route]:
    """Active routes assigned to this gestor, or to nobody (open to all)."""
    return (
        db.query(Route)
        .filter(
            Route.tenant_id == tenant_id,
            Route.activo.is_(True),
            (Route.gestor_id.is_(None)) | (Route.gestor_id == gestor.id),
        )
        .order_by(Route.nombre)
        .all()
    )


@router.get("/routes", response_model=list[RouteOut])
def list_routes(
    tenant_slug: str,
    db: Session = Depends(get_db),
    gestor: Gestor = Depends(get_current_gestor),
):
    tenant = get_tenant(tenant_slug, db)
    return [route_service.route_out(r) for r in _visible_routes(db, tenant.id, gestor)]


@router.post("/routes", response_model=RouteOut)
def create_route(
    tenant_slug: str,
    payload: RouteCreate,
    db: Session = Depends(get_db),
    gestor: Gestor = Depends(get_current_gestor),
):
    """Manual route built from the app: always assigned to the gestor who
    creates it."""
    tenant = get_tenant(tenant_slug, db)
    route = route_service.create_route(db, tenant.id, payload.nombre, payload.meter_ids, gestor.id)
    log_action(db, tenant, gestor, "route.created", target=f"route:{route.id}", actor_type="gestor")
    return route_service.route_out(route)


@router.post("/routes/auto-generate", response_model=list[RouteOut])
def auto_generate_routes(
    tenant_slug: str,
    payload: RouteAutoGenerate,
    db: Session = Depends(get_db),
    gestor: Gestor = Depends(get_current_gestor),
):
    """Same generator the admin uses; routes created here are assigned to the
    calling gestor unless the payload names another one."""
    tenant = get_tenant(tenant_slug, db)
    data = payload.model_dump()
    data["gestor_id"] = payload.gestor_id or gestor.id
    created = route_service.auto_generate(db, tenant.id, **data)
    if not payload.preview:
        log_action(db, tenant, gestor, "route.auto_generated", details=f"rutas={len(created)}", actor_type="gestor")
    return created


@router.post("/routes/{route_id}/start", response_model=RunOut)
def start_route(
    tenant_slug: str,
    route_id: int,
    db: Session = Depends(get_db),
    gestor: Gestor = Depends(get_current_gestor),
):
    """Starts the recorrido (or resumes it if this gestor already has it
    open). The response's `siguiente` is the first meter to read."""
    tenant = get_tenant(tenant_slug, db)
    route = route_service.get_route(db, tenant.id, route_id)
    run = route_service.start_run(db, route, gestor)
    return route_service.run_out(db, run, include_stops=True)


@router.get("/runs/current", response_model=RunOut | None)
def current_run(
    tenant_slug: str,
    db: Session = Depends(get_db),
    gestor: Gestor = Depends(get_current_gestor),
):
    """The recorrido in progress, if any, so the app can offer "continuar"
    after being closed. Null when there isn't one."""
    tenant = get_tenant(tenant_slug, db)
    run = route_service.active_run_for(db, tenant.id, gestor.id)
    return route_service.run_out(db, run, include_stops=True) if run else None


def _own_run(db: Session, tenant_id: int, run_id: int, gestor: Gestor):
    run = route_service.get_run(db, tenant_id, run_id)
    if run.gestor_id != gestor.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Este recorrido pertenece a otro gestor")
    return run


def _open_stop(run, stop_id: int) -> RouteRunStop:
    if run.status != "en_curso":
        raise HTTPException(status.HTTP_409_CONFLICT, "El recorrido ya no está en curso")
    stop = next((s for s in run.stops if s.id == stop_id), None)
    if stop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Parada no encontrada")
    return stop


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(
    tenant_slug: str,
    run_id: int,
    db: Session = Depends(get_db),
    gestor: Gestor = Depends(get_current_gestor),
):
    tenant = get_tenant(tenant_slug, db)
    return route_service.run_out(db, _own_run(db, tenant.id, run_id, gestor), include_stops=True)


@router.post("/runs/{run_id}/stops/{stop_id}/reading", response_model=RunStopResult)
async def submit_stop_reading(
    tenant_slug: str,
    run_id: int,
    stop_id: int,
    valor: float = Form(...),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    foto: list[UploadFile] | None = File(None),
    db: Session = Depends(get_db),
    gestor: Gestor = Depends(get_current_gestor),
):
    """Loads the reading for one stop and advances the recorrido: the
    response carries the updated progress and `siguiente` (null once the
    route is done, at which point status flips to "completado"). Sending it
    again for a stop already read corrects that reading instead of piling up
    a second one."""
    tenant = get_tenant(tenant_slug, db)
    run = _own_run(db, tenant.id, run_id, gestor)
    stop = _open_stop(run, stop_id)
    meter = _get_meter(db, tenant.id, stop.meter_id)

    foto_urls = await _upload_reading_photos(tenant.slug, foto or [])

    if stop.reading_id is not None:
        reading = stop.reading
        now = dt.datetime.utcnow()
        if reading.created_at.year != now.year or reading.created_at.month != now.month:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Esta lectura ya no pertenece al ciclo actual y no se puede editar desde la app",
            )
        reading = update_reading(db, reading, valor, foto_urls=foto_urls or None)
    else:
        reading = register_reading(
            db, meter, valor, gestor_id=gestor.id, foto_urls=foto_urls or None, lat=lat, lon=lon
        )
        stop.reading_id = reading.id

    stop.status = "leido"
    stop.motivo = None
    stop.completed_at = dt.datetime.utcnow()
    db.add(stop)
    db.commit()
    db.refresh(run)
    route_service.maybe_complete(db, run)
    return RunStopResult(run=route_service.run_out(db, run), reading=reading)


@router.post("/runs/{run_id}/stops/{stop_id}/skip", response_model=RunStopResult)
def skip_stop(
    tenant_slug: str,
    run_id: int,
    stop_id: int,
    payload: RunSkip,
    db: Session = Depends(get_db),
    gestor: Gestor = Depends(get_current_gestor),
):
    """Marks a meter as not read (e.g. nobody home, inaccessible) so the
    recorrido can move on."""
    tenant = get_tenant(tenant_slug, db)
    run = _own_run(db, tenant.id, run_id, gestor)
    stop = _open_stop(run, stop_id)
    if stop.status == "leido":
        raise HTTPException(status.HTTP_409_CONFLICT, "Este medidor ya tiene lectura cargada")

    stop.status = "salteado"
    stop.motivo = payload.motivo
    stop.completed_at = dt.datetime.utcnow()
    db.add(stop)
    db.commit()
    db.refresh(run)
    route_service.maybe_complete(db, run)
    return RunStopResult(run=route_service.run_out(db, run))


def _close_run(db: Session, tenant, gestor: Gestor, run_id: int, new_status: str, action: str) -> RunOut:
    run = _own_run(db, tenant.id, run_id, gestor)
    if run.status != "en_curso":
        raise HTTPException(status.HTTP_409_CONFLICT, "El recorrido ya no está en curso")
    run.status = new_status
    run.finished_at = dt.datetime.utcnow()
    db.add(run)
    db.commit()
    db.refresh(run)
    log_action(db, tenant, gestor, action, target=f"run:{run.id}", actor_type="gestor")
    return route_service.run_out(db, run)


@router.post("/runs/{run_id}/finish", response_model=RunOut)
def finish_run(
    tenant_slug: str,
    run_id: int,
    db: Session = Depends(get_db),
    gestor: Gestor = Depends(get_current_gestor),
):
    """Closes the recorrido early; stops still pending stay pending."""
    tenant = get_tenant(tenant_slug, db)
    return _close_run(db, tenant, gestor, run_id, "completado", "route_run.finished")


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
def cancel_run(
    tenant_slug: str,
    run_id: int,
    db: Session = Depends(get_db),
    gestor: Gestor = Depends(get_current_gestor),
):
    tenant = get_tenant(tenant_slug, db)
    return _close_run(db, tenant, gestor, run_id, "cancelado", "route_run.cancelled")
