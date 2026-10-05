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
from app.models import Gestor, Meter, Reading
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
)
from app.services.audit import log_action
from app.services.qr_login import claim as claim_qr_session, get_qr_session, resolve_status
from app.services.readings import register_reading, update_reading
from app.services.storage import UnsupportedPhotoType, upload_reading_photo

import datetime as dt

_UPLOAD_CHUNK_SIZE = 1024 * 1024


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
    ocr_valor: str | None = Form(None),
    ocr_confianza: float | None = Form(None),
    foto: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    gestor: Gestor = Depends(get_current_gestor),
):
    tenant = get_tenant(tenant_slug, db)
    meter = _get_meter(db, tenant.id, meter_id)

    foto_url = None
    if foto is not None:
        content = await _read_capped(foto, settings.max_reading_photo_bytes)
        try:
            foto_url = upload_reading_photo(
                tenant.slug, foto.filename or "lectura.jpg", foto.content_type or "", content
            )
        except UnsupportedPhotoType as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    reading = register_reading(
        db,
        meter,
        valor,
        gestor_id=gestor.id,
        foto_url=foto_url,
        lat=lat,
        lon=lon,
        ocr_valor=ocr_valor,
        ocr_confianza=ocr_confianza,
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
    ocr_valor: str | None = Form(None),
    ocr_confianza: float | None = Form(None),
    foto: UploadFile | None = File(None),
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

    foto_url = None
    if foto is not None:
        content = await _read_capped(foto, settings.max_reading_photo_bytes)
        try:
            foto_url = upload_reading_photo(
                tenant.slug, foto.filename or "lectura.jpg", foto.content_type or "", content
            )
        except UnsupportedPhotoType as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    reading = update_reading(
        db,
        reading,
        valor,
        foto_url=foto_url,
        ocr_valor=ocr_valor,
        ocr_confianza=ocr_confianza,
    )
    log_action(
        db, tenant, gestor, "gestor.reading_updated", target=f"reading:{reading.id}", actor_type="gestor"
    )
    return reading
