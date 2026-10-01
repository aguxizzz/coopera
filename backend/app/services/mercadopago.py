"""Mercado Pago OAuth "Connect" + Checkout Pro.

Each tenant connects *their own* Mercado Pago account via OAuth, so money
flows straight to the cooperativa and Coopera never touches it or sees their
credentials directly. The flow:

1. Admin clicks "Conectar con Mercado Pago" -> `build_authorize_url` sends
   them to MP with a signed `state` carrying the tenant slug.
2. MP redirects back to the single, fixed `mp_redirect_uri` -> the router
   reads the tenant back out of `state` and calls `connect_tenant` to
   exchange the `code` for an access/refresh token pair.
3. `create_preference` uses the tenant's (auto-refreshed) access token to
   open a Checkout Pro payment for one invoice.
4. Mercado Pago calls the tenant's webhook on payment events ->
   `process_webhook_payment` looks the payment up and marks the invoice paid.

Access/refresh tokens are Fernet-encrypted at rest, derived from
`jwt_secret` so no extra secret needs to be configured.
"""
import base64
import datetime as dt
import hashlib
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Invoice, Member, Tenant

MP_AUTHORIZE_URL = "https://auth.mercadopago.com/authorization"
MP_TOKEN_URL = "https://api.mercadopago.com/oauth/token"
MP_PREFERENCE_URL = "https://api.mercadopago.com/checkout/preferences"
MP_PAYMENT_URL = "https://api.mercadopago.com/v1/payments"

STATE_AUDIENCE = "mp_oauth_state"


class MercadoPagoError(Exception):
    pass


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret.encode()).digest())
    return Fernet(key)


def _encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()


def build_state(tenant_slug: str) -> str:
    """Short-lived signed token carrying the tenant through the MP redirect.
    MP just echoes back whatever `state` it was given, so without signing it
    anyone could connect their own MP account to a tenant they don't run."""
    expire = dt.datetime.utcnow() + dt.timedelta(minutes=10)
    payload = {"aud": STATE_AUDIENCE, "tenant_slug": tenant_slug, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def read_state(state: str) -> str:
    try:
        payload = jwt.decode(
            state, settings.jwt_secret, algorithms=["HS256"], audience=STATE_AUDIENCE
        )
    except JWTError as exc:
        raise MercadoPagoError("Estado de conexión inválido o vencido") from exc
    return payload["tenant_slug"]


def build_authorize_url(tenant_slug: str) -> str:
    if not settings.mp_configured:
        raise MercadoPagoError(
            "Mercado Pago no está configurado en esta instancia de Coopera (faltan MP_CLIENT_ID/MP_CLIENT_SECRET)"
        )
    params = {
        "response_type": "code",
        "client_id": settings.mp_client_id,
        "platform_id": "mp",
        "redirect_uri": settings.mp_redirect_uri,
        "state": build_state(tenant_slug),
    }
    return f"{MP_AUTHORIZE_URL}?{urlencode(params)}"


def _save_tokens(db: Session, tenant: Tenant, data: dict) -> None:
    tenant.mp_user_id = str(data["user_id"])
    tenant.mp_access_token = _encrypt(data["access_token"])
    tenant.mp_refresh_token = _encrypt(data["refresh_token"])
    tenant.mp_public_key = data.get("public_key")
    tenant.mp_token_expires_at = dt.datetime.utcnow() + dt.timedelta(seconds=data["expires_in"])
    db.commit()


def connect_tenant(db: Session, tenant: Tenant, code: str) -> None:
    resp = httpx.post(
        MP_TOKEN_URL,
        json={
            "client_id": settings.mp_client_id,
            "client_secret": settings.mp_client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.mp_redirect_uri,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise MercadoPagoError(f"Mercado Pago rechazó la conexión: {resp.text}")
    _save_tokens(db, tenant, resp.json())


def disconnect_tenant(db: Session, tenant: Tenant) -> None:
    tenant.mp_user_id = None
    tenant.mp_access_token = None
    tenant.mp_refresh_token = None
    tenant.mp_public_key = None
    tenant.mp_token_expires_at = None
    db.commit()


def _refresh_access_token(db: Session, tenant: Tenant) -> str:
    resp = httpx.post(
        MP_TOKEN_URL,
        json={
            "client_id": settings.mp_client_id,
            "client_secret": settings.mp_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": _decrypt(tenant.mp_refresh_token),
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise MercadoPagoError(f"No se pudo renovar la conexión con Mercado Pago: {resp.text}")
    data = resp.json()
    _save_tokens(db, tenant, data)
    return data["access_token"]


def get_access_token(db: Session, tenant: Tenant) -> str:
    if not tenant.mp_access_token:
        raise MercadoPagoError("Esta cooperativa todavía no conectó Mercado Pago")
    expires_at = tenant.mp_token_expires_at
    if expires_at and expires_at <= dt.datetime.utcnow() + dt.timedelta(minutes=5):
        return _refresh_access_token(db, tenant)
    return _decrypt(tenant.mp_access_token)


def create_preference(db: Session, tenant: Tenant, member: Member, invoice: Invoice) -> dict:
    access_token = get_access_token(db, tenant)
    period = f"{invoice.period_month:02d}/{invoice.period_year}"
    resp = httpx.post(
        MP_PREFERENCE_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "items": [
                {
                    "title": f"{tenant.name} - Boleta {period} - Socio {member.numero_socio}",
                    "quantity": 1,
                    "currency_id": "ARS",
                    "unit_price": float(invoice.monto),
                }
            ],
            "external_reference": str(invoice.id),
            "notification_url": f"{settings.public_base_url.rstrip('/')}/api/t/{tenant.slug}/mp/webhook",
            "back_urls": {
                "success": f"{settings.frontend_base_url.rstrip('/')}/{tenant.slug}?pago=exito",
                "pending": f"{settings.frontend_base_url.rstrip('/')}/{tenant.slug}?pago=pendiente",
                "failure": f"{settings.frontend_base_url.rstrip('/')}/{tenant.slug}?pago=error",
            },
            "auto_return": "approved",
        },
        timeout=15,
    )
    if resp.status_code not in (200, 201):
        raise MercadoPagoError(f"No se pudo generar el pago: {resp.text}")
    data = resp.json()
    invoice.mp_preference_id = data["id"]
    db.commit()
    return data


def process_webhook_payment(db: Session, tenant: Tenant, payment_id: str) -> Invoice | None:
    access_token = get_access_token(db, tenant)
    resp = httpx.get(
        f"{MP_PAYMENT_URL}/{payment_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if resp.status_code != 200:
        raise MercadoPagoError(f"No se pudo consultar el pago: {resp.text}")
    data = resp.json()

    external_reference = data.get("external_reference")
    if not external_reference or not external_reference.isdigit():
        return None

    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == int(external_reference), Invoice.tenant_id == tenant.id)
        .first()
    )
    if invoice is None:
        return None

    invoice.mp_payment_id = str(data["id"])
    if data.get("status") == "approved":
        invoice.pagado = True
    db.commit()
    return invoice
