"""Macro Click de Pago (Banco Macro) - integración NO OFICIAL (ver
`app/services/macroclick.py` y `macroclick/plan.md` en la raíz del repo).

Dos endpoints público-facing, ninguno con token de admin:

- `checkout-form`: el socio llega acá navegado desde el frontend
  (`window.location.href = init_point`) con un token de corta duración
  minteado en `routers/public.py` tras validar numero_socio/identificador.
  Sirve un HTML que se auto-envía por POST al dominio de Macro.
- `webhook`: llamado server-to-server por Macro. ⚠️ A diferencia de
  Helipagos, el protocolo reconstruido no tiene ningún secreto/firma para
  validar que la notificación viene realmente de Macro - ver el warning en
  `macroclick.py`.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Invoice, Member, Tenant
from app.services.macroclick import (
    MacroclickError,
    build_checkout_form_html,
    process_webhook_payment,
    read_checkout_token,
)

router = APIRouter(tags=["macroclick"])


@router.get("/api/t/{tenant_slug}/macroclick/checkout-form/{token}", response_class=HTMLResponse)
async def macroclick_checkout_form(tenant_slug: str, token: str, request: Request, db: Session = Depends(get_db)):
    try:
        token_slug, invoice_id = read_checkout_token(token)
    except MacroclickError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    if token_slug != tenant_slug:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token de pago inválido")

    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cooperativa no encontrada")

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.tenant_id == tenant.id).first()
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Factura no encontrada")
    if invoice.pagado:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta factura ya está pagada")

    member = db.query(Member).filter(Member.id == invoice.member_id).first()

    try:
        html = build_checkout_form_html(tenant, member, invoice, client_ip=request.client.host if request.client else "")
    except MacroclickError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    return HTMLResponse(html)


@router.post("/api/t/{tenant_slug}/macroclick/webhook")
async def macroclick_webhook(tenant_slug: str, request: Request, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if tenant is None or not tenant.macroclick_comercio_id:
        # No revelar si el slug existe, y no fallar en un webhook para un
        # tenant que desde entonces desconectó Macro Click de Pago.
        return {"status": "ignored"}

    payload = await request.json() if "application/json" in request.headers.get("content-type", "") else {}

    process_webhook_payment(db, tenant, payload)
    return {"status": "ok"}
