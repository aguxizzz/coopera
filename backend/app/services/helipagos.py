"""Helipagos checkout simple: a single "solicitud de pago" per invoice.

Unlike Mercado Pago, Helipagos has no OAuth/marketplace flow: each tenant
signs up with Helipagos on their own and pastes a single Bearer token (plus
the shared-secret "apikey" Helipagos sends on webhook calls) into a form.
There's no platform-level credential to configure in Coopera.

Flow:

1. Admin pastes their Helipagos token + webhook apikey -> `save_credentials`
   stores both Fernet-encrypted (same scheme as `mercadopago.py`).
2. `create_solicitud_pago` opens a "solicitud de pago" (checkout) for one
   invoice, reusing a still-pending one instead of creating a duplicate.
3. Helipagos calls the tenant's webhook on payment events ->
   `process_webhook_payment` looks the invoice up by `helipagos_id_sp` and
   marks it paid.
"""
import base64
import datetime as dt
import hashlib

import httpx
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Invoice, Member, Tenant

HELIPAGOS_SANDBOX_BASE = "https://sandbox.helipagos.com"
HELIPAGOS_PROD_BASE = "https://api.helipagos.com"

SOLICITUD_PAGO_PATH = "/api/solicitud_pago/v1/checkout/solicitud_pago"
GET_SOLICITUD_PAGO_PATH = "/api/solicitud_pago/v1/get_solicitud_pago"

# Estados de la solicitud de pago en los que todavía se puede usar el
# checkout existente en vez de crear uno nuevo. Cualquier otro estado
# (VENCIDA, RECHAZADA, ANULADA, PROCESADA, ACREDITADA, DEVUELTA, CONTRACARGO)
# requiere una solicitud nueva.
REUSABLE_STATES = {"GENERADA"}

# Estados que indican que el pago se realizó. Marcamos pagado en PROCESADA
# (pago realizado) en vez de esperar ACREDITADA (liquidado a la cuenta), igual
# criterio que usamos con "approved" de Mercado Pago, para no demorar la
# experiencia del socio.
PAID_STATES = {"PROCESADA", "ACREDITADA"}


class HelipagosError(Exception):
    pass


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret.encode()).digest())
    return Fernet(key)


def _encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()


def _base_url(tenant: Tenant) -> str:
    return HELIPAGOS_PROD_BASE if tenant.helipagos_environment == "production" else HELIPAGOS_SANDBOX_BASE


def save_credentials(db: Session, tenant: Tenant, token: str, webhook_apikey: str, environment: str) -> None:
    tenant.helipagos_token = _encrypt(token)
    tenant.helipagos_webhook_apikey = _encrypt(webhook_apikey)
    tenant.helipagos_environment = environment
    db.commit()


def disconnect_tenant(db: Session, tenant: Tenant) -> None:
    tenant.helipagos_token = None
    tenant.helipagos_webhook_apikey = None
    tenant.helipagos_environment = "sandbox"
    db.commit()


def _get_access_token(tenant: Tenant) -> str:
    if not tenant.helipagos_token:
        raise HelipagosError("Esta cooperativa todavía no conectó Helipagos")
    return _decrypt(tenant.helipagos_token)


def _get_solicitud_pago(tenant: Tenant, id_sp: str) -> dict | None:
    token = _get_access_token(tenant)
    resp = httpx.get(
        f"{_base_url(tenant)}{GET_SOLICITUD_PAGO_PATH}",
        headers={"Authorization": f"Bearer {token}"},
        params={"id": id_sp},
        timeout=15,
    )
    if resp.status_code != 200:
        raise HelipagosError(f"No se pudo consultar la solicitud de pago: {resp.text}")
    data = resp.json()
    items = data if isinstance(data, list) else [data]
    return items[0] if items else None


def create_solicitud_pago(db: Session, tenant: Tenant, member: Member, invoice: Invoice) -> dict:
    token = _get_access_token(tenant)

    if invoice.helipagos_id_sp:
        existing = _get_solicitud_pago(tenant, invoice.helipagos_id_sp)
        if existing and existing.get("estado_pago") in REUSABLE_STATES:
            return existing

    period = f"{invoice.period_month:02d}/{invoice.period_year}"
    fecha_vto = invoice.vencimiento or (dt.date.today() + dt.timedelta(days=30))

    resp = httpx.post(
        f"{_base_url(tenant)}{SOLICITUD_PAGO_PATH}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "importe": int(round(float(invoice.monto) * 100)),
            "fecha_vto": fecha_vto.isoformat(),
            "descripcion": f"{tenant.name} - Boleta {period} - Socio {member.numero_socio}"[:64],
            "referencia_externa": f"inv-{invoice.id}",
            "url_redirect": f"{settings.frontend_base_url.rstrip('/')}/{tenant.slug}?pago=exito",
            "webhook": f"{settings.public_base_url.rstrip('/')}/api/t/{tenant.slug}/helipagos/webhook",
            "qr": False,
        },
        timeout=15,
    )
    if resp.status_code not in (200, 201):
        raise HelipagosError(f"No se pudo generar el pago: {resp.text}")

    data = resp.json()
    invoice.helipagos_id_sp = str(data["id_sp"])
    db.commit()
    return data


def process_webhook_payment(db: Session, tenant: Tenant, payload: dict) -> Invoice | None:
    id_sp = payload.get("id_sp")
    if id_sp is None:
        return None

    invoice = (
        db.query(Invoice)
        .filter(Invoice.helipagos_id_sp == str(id_sp), Invoice.tenant_id == tenant.id)
        .first()
    )
    if invoice is None:
        return None

    if payload.get("estado") in PAID_STATES:
        invoice.pagado = True
    db.commit()
    return invoice
