from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_tenant
from app.models import Invoice, Member, Tenant
from app.rate_limit import limiter
from app.schemas import (
    InvoiceOut,
    MemberAccountOut,
    MemberLookupRequest,
    PayInvoiceRequest,
    PayInvoiceResponse,
    TenantPublic,
)
from app.services.helipagos import HelipagosError
from app.services.helipagos import create_solicitud_pago as create_helipagos_solicitud_pago
from app.services.macroclick import build_checkout_token
from app.services.mercadopago import MercadoPagoError, create_preference
from app.services.pdf import build_boleta_pdf

router = APIRouter(prefix="/api/t/{tenant_slug}", tags=["public"])


def _find_member(db: Session, tenant: Tenant, numero_socio: str, identificador: str) -> Member:
    member = (
        db.query(Member)
        .filter(
            Member.tenant_id == tenant.id,
            Member.numero_socio == numero_socio.strip(),
            Member.identificador == identificador.strip(),
        )
        .first()
    )
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos un socio con esos datos")
    return member


def _saldo_total(db: Session, member: Member) -> float:
    saldo = (
        db.query(func.coalesce(func.sum(Invoice.monto), 0))
        .filter(Invoice.member_id == member.id, Invoice.pagado.is_(False))
        .scalar()
    )
    return float(saldo or 0)


@router.get("", response_model=TenantPublic)
def get_tenant_info(tenant_slug: str, db: Session = Depends(get_db)):
    return get_tenant(tenant_slug, db)


@router.post("/lookup", response_model=MemberAccountOut)
@limiter.limit("10/minute")
def lookup_member(
    request: Request, tenant_slug: str, payload: MemberLookupRequest, db: Session = Depends(get_db)
):
    tenant = get_tenant(tenant_slug, db)
    member = _find_member(db, tenant, payload.numero_socio, payload.identificador)

    historial = (
        db.query(Invoice)
        .filter(Invoice.member_id == member.id)
        .order_by(Invoice.period_year.desc(), Invoice.period_month.desc())
        .limit(12)
        .all()
    )
    ultima = historial[0] if historial else None

    return MemberAccountOut(
        numero_socio=member.numero_socio,
        nombre=member.nombre,
        saldo_total=_saldo_total(db, member),
        ultima_factura=InvoiceOut.model_validate(ultima) if ultima else None,
        historial=[InvoiceOut.model_validate(i) for i in historial],
        mp_alias=tenant.mp_alias,
        mp_cbu=tenant.mp_cbu,
        mp_titular=tenant.mp_titular,
        mp_connected=bool(tenant.mp_access_token),
        helipagos_connected=bool(tenant.helipagos_token),
        macroclick_connected=bool(tenant.macroclick_comercio_id),
    )


@router.post("/invoices/{invoice_id}/pay", response_model=PayInvoiceResponse)
@limiter.limit("10/minute")
def pay_invoice(
    request: Request,
    tenant_slug: str,
    invoice_id: int,
    payload: PayInvoiceRequest,
    db: Session = Depends(get_db),
):
    tenant = get_tenant(tenant_slug, db)
    member = _find_member(db, tenant, payload.numero_socio, payload.identificador)

    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.member_id == member.id)
        .first()
    )
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Factura no encontrada")
    if invoice.pagado:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta factura ya está pagada")
    if not tenant.mp_access_token:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Esta cooperativa todavía no conectó Mercado Pago"
        )

    try:
        preference = create_preference(db, tenant, member, invoice)
    except MercadoPagoError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

    return PayInvoiceResponse(init_point=preference["init_point"])


@router.post("/invoices/{invoice_id}/pay-helipagos", response_model=PayInvoiceResponse)
@limiter.limit("10/minute")
def pay_invoice_helipagos(
    request: Request,
    tenant_slug: str,
    invoice_id: int,
    payload: PayInvoiceRequest,
    db: Session = Depends(get_db),
):
    tenant = get_tenant(tenant_slug, db)
    member = _find_member(db, tenant, payload.numero_socio, payload.identificador)

    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.member_id == member.id)
        .first()
    )
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Factura no encontrada")
    if invoice.pagado:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta factura ya está pagada")
    if not tenant.helipagos_token:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Esta cooperativa todavía no conectó Helipagos"
        )

    try:
        data = create_helipagos_solicitud_pago(db, tenant, member, invoice)
    except HelipagosError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

    return PayInvoiceResponse(init_point=data.get("checkout_url") or data["short_url"])


@router.post("/invoices/{invoice_id}/pay-macroclick", response_model=PayInvoiceResponse)
@limiter.limit("10/minute")
def pay_invoice_macroclick(
    request: Request,
    tenant_slug: str,
    invoice_id: int,
    payload: PayInvoiceRequest,
    db: Session = Depends(get_db),
):
    """Macro Click de Pago - integración NO OFICIAL (ver
    app/services/macroclick.py). A diferencia de MP/Helipagos no hay una URL
    de checkout de Macro para devolver de antemano: `init_point` apunta a
    nuestro propio endpoint (`routers/macroclick.py`), que sirve el form
    auto-submit."""
    tenant = get_tenant(tenant_slug, db)
    member = _find_member(db, tenant, payload.numero_socio, payload.identificador)

    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.member_id == member.id)
        .first()
    )
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Factura no encontrada")
    if invoice.pagado:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta factura ya está pagada")
    if not tenant.macroclick_comercio_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Esta cooperativa todavía no conectó Macro Click de Pago"
        )

    token = build_checkout_token(tenant.slug, invoice.id)
    init_point = f"{settings.public_base_url.rstrip('/')}/api/t/{tenant.slug}/macroclick/checkout-form/{token}"
    return PayInvoiceResponse(init_point=init_point)


@router.get("/boleta.pdf")
@limiter.limit("10/minute")
def download_boleta(
    request: Request,
    tenant_slug: str,
    numero_socio: str,
    identificador: str,
    db: Session = Depends(get_db),
):
    tenant = get_tenant(tenant_slug, db)
    member = _find_member(db, tenant, numero_socio, identificador)

    invoice = (
        db.query(Invoice)
        .filter(Invoice.member_id == member.id)
        .order_by(Invoice.period_year.desc(), Invoice.period_month.desc())
        .first()
    )
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El socio no tiene boletas cargadas")

    pdf_bytes = build_boleta_pdf(tenant, member, invoice, _saldo_total(db, member))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=boleta-{member.numero_socio}.pdf"},
    )
