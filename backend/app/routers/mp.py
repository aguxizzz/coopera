"""Mercado Pago-facing endpoints: the OAuth redirect target (visited by the
admin's browser after they authorize Coopera's app) and the per-tenant
payment webhook (called server-to-server by Mercado Pago). Neither carries an
admin/platform token — the OAuth leg is authenticated via the signed `state`,
and the webhook only reveals/changes payment status for a single invoice
that Mercado Pago itself just processed."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Tenant
from app.services.mercadopago import (
    MercadoPagoError,
    connect_tenant,
    process_webhook_payment,
    read_state,
)

router = APIRouter(tags=["mercadopago"])


@router.get("/api/mp/oauth/callback")
def mp_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    frontend = settings.frontend_base_url.rstrip("/")

    if error or not code or not state:
        return RedirectResponse(f"{frontend}/admin?mp=error")

    try:
        tenant_slug = read_state(state)
    except MercadoPagoError:
        return RedirectResponse(f"{frontend}/admin?mp=error")

    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if tenant is None:
        return RedirectResponse(f"{frontend}/admin?mp=error")

    try:
        connect_tenant(db, tenant, code)
    except MercadoPagoError:
        return RedirectResponse(f"{frontend}/{tenant_slug}/admin/dashboard?mp=error")

    return RedirectResponse(f"{frontend}/{tenant_slug}/admin/dashboard?mp=success")


@router.post("/api/t/{tenant_slug}/mp/webhook")
async def mp_webhook(tenant_slug: str, request: Request, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if tenant is None or not tenant.mp_access_token:
        # Don't leak whether a slug exists, and don't error on a webhook for
        # a tenant that has since disconnected — just ignore it.
        return {"status": "ignored"}

    payload = await request.json() if "application/json" in request.headers.get("content-type", "") else {}

    topic = payload.get("type") or request.query_params.get("topic")
    payment_id = (payload.get("data") or {}).get("id") or request.query_params.get("id")

    if topic != "payment" or not payment_id:
        return {"status": "ignored"}

    try:
        process_webhook_payment(db, tenant, str(payment_id))
    except MercadoPagoError:
        # MP retries on non-2xx; a transient failure here (token refresh
        # down, rate limit) will just be retried by MP, so still ack it.
        return {"status": "error"}

    return {"status": "ok"}
