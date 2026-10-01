from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_admin, verify_password
from app.config import settings
from app.database import get_db
from app.deps import get_tenant
from app.models import AdminUser, Invoice, Member, Tenant
from app.rate_limit import limiter
from app.schemas import (
    AdminLogin,
    DeleteMembersRequest,
    DeleteMembersResult,
    ImportResult,
    InvoiceOut,
    MemberRow,
    MpConnectUrlOut,
    MpStatusOut,
    TenantSettingsOut,
    TenantSettingsUpdate,
    TokenResponse,
    UpdateInvoicePagado,
)
from app.services.importer import ImportError_, import_spreadsheet
from app.services.mercadopago import MercadoPagoError, build_authorize_url, disconnect_tenant
from app.services.storage import UnsupportedLogoType, delete_logo, upload_logo

router = APIRouter(prefix="/api/t/{tenant_slug}/admin", tags=["admin"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(request: Request, tenant_slug: str, payload: AdminLogin, db: Session = Depends(get_db)):
    tenant = get_tenant(tenant_slug, db)
    admin = (
        db.query(AdminUser)
        .filter(AdminUser.tenant_id == tenant.id, AdminUser.email == payload.email)
        .first()
    )
    if admin is None or not verify_password(payload.password, admin.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas")
    token = create_access_token(admin.id, tenant.id)
    return TokenResponse(access_token=token)


@router.post("/import", response_model=ImportResult)
async def import_members(
    tenant_slug: str,
    period_year: int = Form(...),
    period_month: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)

    content = await file.read()
    try:
        batch, created, updated = import_spreadsheet(
            db, tenant, file.filename or "planilla", content, period_year, period_month
        )
    except ImportError_ as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    return ImportResult(
        period_year=period_year,
        period_month=period_month,
        rows_processed=batch.row_count,
        members_created=created,
        members_updated=updated,
    )


@router.get("/members", response_model=list[MemberRow])
def list_members(
    tenant_slug: str,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    members = db.query(Member).filter(Member.tenant_id == tenant.id).order_by(Member.numero_socio).all()

    rows = []
    for m in members:
        saldo = (
            db.query(func.coalesce(func.sum(Invoice.monto), 0))
            .filter(Invoice.member_id == m.id, Invoice.pagado.is_(False))
            .scalar()
        )
        rows.append(
            MemberRow(
                id=m.id,
                numero_socio=m.numero_socio,
                nombre=m.nombre,
                identificador=m.identificador,
                saldo_total=float(saldo or 0),
            )
        )
    return rows


@router.get("/members/{member_id}/invoices", response_model=list[InvoiceOut])
def list_member_invoices(
    tenant_slug: str,
    member_id: int,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    member = (
        db.query(Member)
        .filter(Member.id == member_id, Member.tenant_id == tenant.id)
        .first()
    )
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Socio no encontrado")
    return (
        db.query(Invoice)
        .filter(Invoice.member_id == member.id)
        .order_by(Invoice.period_year.desc(), Invoice.period_month.desc())
        .all()
    )


@router.patch("/invoices/{invoice_id}", response_model=InvoiceOut)
def update_invoice_pagado(
    tenant_slug: str,
    invoice_id: int,
    payload: UpdateInvoicePagado,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.tenant_id == tenant.id)
        .first()
    )
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Factura no encontrada")
    invoice.pagado = payload.pagado
    db.commit()
    db.refresh(invoice)
    return invoice


@router.delete("/members/{member_id}", response_model=DeleteMembersResult)
def delete_member(
    tenant_slug: str,
    member_id: int,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    member = (
        db.query(Member)
        .filter(Member.id == member_id, Member.tenant_id == tenant.id)
        .first()
    )
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Socio no encontrado")
    db.delete(member)
    db.commit()
    return DeleteMembersResult(deleted=1)


@router.post("/members/delete", response_model=DeleteMembersResult)
def delete_members(
    tenant_slug: str,
    payload: DeleteMembersRequest,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    if not payload.member_ids:
        return DeleteMembersResult(deleted=0)
    members = (
        db.query(Member)
        .filter(Member.tenant_id == tenant.id, Member.id.in_(payload.member_ids))
        .all()
    )
    for member in members:
        db.delete(member)
    db.commit()
    return DeleteMembersResult(deleted=len(members))


@router.get("/settings", response_model=TenantSettingsOut)
def get_settings(
    tenant_slug: str,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    return get_tenant(tenant_slug, db)


@router.put("/settings", response_model=TenantSettingsOut)
def update_settings(
    tenant_slug: str,
    payload: TenantSettingsUpdate,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)
    db.commit()
    db.refresh(tenant)
    return tenant


@router.post("/logo", response_model=TenantSettingsOut)
async def upload_tenant_logo(
    tenant_slug: str,
    kind: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    if kind not in ("primary", "secondary"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "kind debe ser 'primary' o 'secondary'")

    tenant = get_tenant(tenant_slug, db)
    content = await file.read()
    try:
        url = upload_logo(
            tenant.slug, kind, file.filename or "logo", file.content_type or "", content
        )
    except UnsupportedLogoType as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    old_url = tenant.logo_primary_url if kind == "primary" else tenant.logo_secondary_url
    if kind == "primary":
        tenant.logo_primary_url = url
    else:
        tenant.logo_secondary_url = url
    db.commit()
    db.refresh(tenant)

    if old_url:
        delete_logo(old_url)

    return tenant


@router.get("/mp/status", response_model=MpStatusOut)
def mp_status(
    tenant_slug: str,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    return MpStatusOut(
        configured=settings.mp_configured,
        connected=bool(tenant.mp_access_token),
        mp_user_id=tenant.mp_user_id,
    )


@router.get("/mp/connect-url", response_model=MpConnectUrlOut)
def mp_connect_url(
    tenant_slug: str,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    try:
        return MpConnectUrlOut(url=build_authorize_url(tenant.slug))
    except MercadoPagoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.delete("/mp", response_model=MpStatusOut)
def mp_disconnect(
    tenant_slug: str,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    disconnect_tenant(db, tenant)
    return MpStatusOut(configured=settings.mp_configured, connected=False, mp_user_id=None)


@router.delete("/logo", response_model=TenantSettingsOut)
def delete_tenant_logo(
    tenant_slug: str,
    kind: str,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    if kind not in ("primary", "secondary"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "kind debe ser 'primary' o 'secondary'")

    tenant = get_tenant(tenant_slug, db)
    old_url = tenant.logo_primary_url if kind == "primary" else tenant.logo_secondary_url
    if kind == "primary":
        tenant.logo_primary_url = None
    else:
        tenant.logo_secondary_url = None
    db.commit()
    db.refresh(tenant)

    if old_url:
        delete_logo(old_url)

    return tenant
