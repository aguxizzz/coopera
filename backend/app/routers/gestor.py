from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth import create_gestor_token, get_current_gestor, verify_password
from app.config import settings
from app.database import get_db
from app.deps import get_tenant
from app.models import Gestor, Meter, Reading
from app.schemas import GestorLogin, MeterOut, ReadingOut, TokenResponse
from app.services.readings import register_reading
from app.services.storage import UnsupportedPhotoType, upload_reading_photo

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


@router.post("/login", response_model=TokenResponse)
def login(tenant_slug: str, payload: GestorLogin, db: Session = Depends(get_db)):
    tenant = get_tenant(tenant_slug, db)
    gestor = (
        db.query(Gestor)
        .filter(Gestor.tenant_id == tenant.id, Gestor.email == payload.email)
        .first()
    )
    if gestor is None or not verify_password(payload.password, gestor.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas")
    if not gestor.activo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Gestor inactivo")
    token = create_gestor_token(gestor.id, tenant.id)
    return TokenResponse(access_token=token)


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
