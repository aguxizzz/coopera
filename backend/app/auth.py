import datetime as dt
import hashlib
import secrets

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_tenant
from app.models import AdminUser, Gestor, PlatformUser, Tenant

bearer_scheme = HTTPBearer(auto_error=False)

_REFRESH_TOKEN_BYTES = 32


class PlatformActor:
    """Stand-in for AdminUser when a platform (dev) token is used to access a
    tenant-scoped admin endpoint. Duck-types the attributes those endpoints
    rely on (none beyond dependency injection today) while flagging that the
    request came from platform staff, not a tenant admin."""

    def __init__(self, platform_user: PlatformUser, tenant_id: int):
        self.id = platform_user.id
        self.email = platform_user.email
        self.tenant_id = tenant_id
        self.is_platform = True
        self.role = "owner"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(admin_id: int, tenant_id: int) -> str:
    expire = dt.datetime.utcnow() + dt.timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(admin_id), "tenant_id": tenant_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_platform_token(platform_user_id: int) -> str:
    expire = dt.datetime.utcnow() + dt.timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(platform_user_id), "platform": True, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_gestor_access_token(gestor_id: int, tenant_id: int) -> str:
    expire = dt.datetime.utcnow() + dt.timedelta(minutes=settings.jwt_gestor_access_expire_minutes)
    payload = {"sub": str(gestor_id), "tenant_id": tenant_id, "gestor": True, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_device_token(tenant_id: int) -> str:
    """Short-lived token proving the device knows the cooperativa's shared
    gestor password. Good for nothing but /gestor/select-profile — it has no
    gestor identity, just the tenant it was issued for."""
    expire = dt.datetime.utcnow() + dt.timedelta(minutes=settings.jwt_device_expire_minutes)
    payload = {"tenant_id": tenant_id, "device": True, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_device_token(tenant_id: int, device_token: str) -> None:
    """Validates a device token against the given tenant. Raises 401 if it's
    invalid, expired, or scoped to a different cooperativa."""
    try:
        payload = jwt.decode(device_token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de dispositivo inválido")
    if not payload.get("device") or payload.get("tenant_id") != tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de dispositivo inválido")


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_gestor_refresh_token(db: Session, gestor: Gestor) -> str:
    """Mints a new opaque refresh token for the gestor, storing only its hash
    (rotated out on every refresh) so a leaked DB snapshot can't be replayed
    as a live session."""
    token = secrets.token_urlsafe(_REFRESH_TOKEN_BYTES)
    gestor.refresh_token_hash = _hash_refresh_token(token)
    gestor.refresh_token_expires_at = dt.datetime.utcnow() + dt.timedelta(
        days=settings.jwt_gestor_refresh_expire_days
    )
    db.add(gestor)
    db.commit()
    return token


def consume_gestor_refresh_token(db: Session, tenant_id: int, refresh_token: str) -> Gestor:
    """Validates a refresh token and returns the gestor it belongs to. Does
    NOT rotate it — the caller mints and persists the replacement once it has
    successfully issued a new access token, via issue_gestor_refresh_token."""
    token_hash = _hash_refresh_token(refresh_token)
    gestor = (
        db.query(Gestor)
        .filter(Gestor.tenant_id == tenant_id, Gestor.refresh_token_hash == token_hash)
        .first()
    )
    if gestor is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token inválido")
    if (
        gestor.refresh_token_expires_at is None
        or gestor.refresh_token_expires_at < dt.datetime.utcnow()
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token expirado")
    if not gestor.activo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Gestor inactivo")
    return gestor


def _decode(credentials: HTTPAuthorizationCredentials | None) -> dict:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No autenticado")
    try:
        return jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido")


def get_current_platform_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> PlatformUser:
    payload = _decode(credentials)
    if not payload.get("platform"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Token no es de un usuario de plataforma")
    platform_user = db.get(PlatformUser, int(payload["sub"]))
    if platform_user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario no encontrado")
    return platform_user


def get_current_admin(
    tenant_slug: str,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AdminUser:
    tenant = get_tenant(tenant_slug, db)
    payload = _decode(credentials)

    if payload.get("platform"):
        platform_user = db.get(PlatformUser, int(payload["sub"]))
        if platform_user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario no encontrado")
        return PlatformActor(platform_user, tenant.id)

    if payload.get("tenant_id") != tenant.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Token no corresponde a esta cooperativa")

    admin = db.get(AdminUser, int(payload["sub"]))
    if admin is None or admin.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario no encontrado")
    return admin


def get_current_gestor(
    tenant_slug: str,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Gestor:
    tenant = get_tenant(tenant_slug, db)
    payload = _decode(credentials)
    if not payload.get("gestor"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Token no es de un gestor")
    if payload.get("tenant_id") != tenant.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Token no corresponde a esta cooperativa")

    gestor = db.get(Gestor, int(payload["sub"]))
    if gestor is None or gestor.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario no encontrado")
    if not gestor.activo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Gestor inactivo")
    return gestor


def require_owner(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    """Gate for actions reserved to a tenant's owner admins: managing other
    admins and connecting/disconnecting Mercado Pago. Platform staff always
    pass (they act as an implicit owner for troubleshooting)."""
    if getattr(admin, "is_platform", False) or admin.role == "owner":
        return admin
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "Se requiere rol de administrador principal (owner) para esta acción",
    )
