"""Helipagos-facing endpoint: the per-tenant payment webhook (called
server-to-server by Helipagos). It carries no admin/platform token — it's
authenticated via a shared-secret "apikey" header the tenant configured when
connecting Helipagos."""

import hmac

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Tenant
from app.services.helipagos import HelipagosError, _decrypt, process_webhook_payment

router = APIRouter(tags=["helipagos"])


@router.post("/api/t/{tenant_slug}/helipagos/webhook")
async def helipagos_webhook(tenant_slug: str, request: Request, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if tenant is None or not tenant.helipagos_webhook_apikey:
        # Don't leak whether a slug exists, and don't error on a webhook for
        # a tenant that has since disconnected — just ignore it.
        return {"status": "ignored"}

    incoming_key = request.headers.get("apikey", "")
    expected_key = _decrypt(tenant.helipagos_webhook_apikey)
    if not incoming_key or not hmac.compare_digest(incoming_key, expected_key):
        # No revelar si el apikey configurado es correcto o no.
        return {"status": "ignored"}

    payload = await request.json() if "application/json" in request.headers.get("content-type", "") else {}

    try:
        process_webhook_payment(db, tenant, payload)
    except HelipagosError:
        # Helipagos reintenta 3 veces cada 10 min si no recibe 200 — un
        # fallo transitorio se reintentará solo, así que igual acusamos 200.
        return {"status": "error"}

    return {"status": "ok"}
