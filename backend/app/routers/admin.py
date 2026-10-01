import datetime as dt

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_admin, hash_password, require_owner, verify_password
from app.config import settings
from app.database import get_db
from app.deps import get_tenant
from app.models import AdminUser, AuditLog, Invoice, Member, Tenant
from app.rate_limit import limiter
from app.schemas import (
    AdminCreate,
    AdminLogin,
    AdminPasswordReset,
    AdminRoleUpdate,
    AdminUserOut,
    AuditLogOut,
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
from app.services.audit import log_action
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


@router.get("/me", response_model=AdminUserOut)
def me(
    tenant_slug: str,
    admin: AdminUser = Depends(get_current_admin),
):
    if getattr(admin, "is_platform", False):
        return AdminUserOut(id=admin.id, email=admin.email, role="owner", created_at=dt.datetime.utcnow())
    return admin


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
    log_action(
        db, tenant, _admin, "invoice.pagado_updated",
        target=f"invoice:{invoice.id}", details=f"pagado={payload.pagado}",
    )
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
    log_action(db, tenant, _admin, "member.deleted", target=f"member:{member_id}")
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
    if members:
        log_action(db, tenant, _admin, "member.bulk_deleted", details=f"count={len(members)}")
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
    changed_fields = list(payload.model_dump(exclude_unset=True).keys())
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)
    db.commit()
    db.refresh(tenant)
    if changed_fields:
        log_action(db, tenant, _admin, "settings.updated", details=", ".join(changed_fields))
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
    admin: AdminUser = Depends(require_owner),
):
    tenant = get_tenant(tenant_slug, db)
    try:
        url = build_authorize_url(tenant.slug)
    except MercadoPagoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    log_action(db, tenant, admin, "mp.connect_url_requested")
    return MpConnectUrlOut(url=url)


@router.delete("/mp", response_model=MpStatusOut)
def mp_disconnect(
    tenant_slug: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_owner),
):
    tenant = get_tenant(tenant_slug, db)
    disconnect_tenant(db, tenant)
    log_action(db, tenant, admin, "mp.disconnected")
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


# --- Admin management (roles) ---------------------------------------------
# Only owners can see/manage this tenant's admin roster. Connecting or
# disconnecting Mercado Pago is also owner-only (see above), so promoting
# someone to owner is effectively granting them that power.


@router.get("/admins", response_model=list[AdminUserOut])
def list_admins(
    tenant_slug: str,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(require_owner),
):
    tenant = get_tenant(tenant_slug, db)
    return db.query(AdminUser).filter(AdminUser.tenant_id == tenant.id).order_by(AdminUser.email).all()


@router.post("/admins", response_model=AdminUserOut)
def create_admin(
    tenant_slug: str,
    payload: AdminCreate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_owner),
):
    tenant = get_tenant(tenant_slug, db)
    if db.query(AdminUser).filter(AdminUser.tenant_id == tenant.id, AdminUser.email == payload.email).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ya existe un admin con ese email en esta cooperativa")

    new_admin = AdminUser(
        tenant_id=tenant.id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    log_action(
        db, tenant, admin, "admin.created",
        target=f"admin:{new_admin.id}", details=f"email={new_admin.email}, role={new_admin.role}",
    )
    return new_admin


def _require_not_last_owner(db: Session, tenant: Tenant, admin_id: int) -> None:
    owners = (
        db.query(AdminUser)
        .filter(AdminUser.tenant_id == tenant.id, AdminUser.role == "owner", AdminUser.id != admin_id)
        .count()
    )
    if owners == 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "La cooperativa debe conservar al menos un administrador owner",
        )


@router.patch("/admins/{admin_id}/role", response_model=AdminUserOut)
def update_admin_role(
    tenant_slug: str,
    admin_id: int,
    payload: AdminRoleUpdate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_owner),
):
    tenant = get_tenant(tenant_slug, db)
    target_admin = (
        db.query(AdminUser).filter(AdminUser.id == admin_id, AdminUser.tenant_id == tenant.id).first()
    )
    if target_admin is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Admin no encontrado")
    if target_admin.role == "owner" and payload.role != "owner":
        _require_not_last_owner(db, tenant, target_admin.id)

    target_admin.role = payload.role
    db.commit()
    db.refresh(target_admin)
    log_action(
        db, tenant, admin, "admin.role_updated",
        target=f"admin:{target_admin.id}", details=f"role={payload.role}",
    )
    return target_admin


@router.post("/admins/{admin_id}/reset-password", response_model=AdminUserOut)
def reset_admin_password(
    tenant_slug: str,
    admin_id: int,
    payload: AdminPasswordReset,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_owner),
):
    tenant = get_tenant(tenant_slug, db)
    target_admin = (
        db.query(AdminUser).filter(AdminUser.id == admin_id, AdminUser.tenant_id == tenant.id).first()
    )
    if target_admin is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Admin no encontrado")
    target_admin.hashed_password = hash_password(payload.password)
    db.commit()
    db.refresh(target_admin)
    log_action(db, tenant, admin, "admin.password_reset", target=f"admin:{target_admin.id}")
    return target_admin


@router.delete("/admins/{admin_id}", response_model=AdminUserOut)
def delete_admin(
    tenant_slug: str,
    admin_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_owner),
):
    tenant = get_tenant(tenant_slug, db)
    target_admin = (
        db.query(AdminUser).filter(AdminUser.id == admin_id, AdminUser.tenant_id == tenant.id).first()
    )
    if target_admin is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Admin no encontrado")
    if not getattr(admin, "is_platform", False) and target_admin.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No podés eliminarte a vos mismo")
    if target_admin.role == "owner":
        _require_not_last_owner(db, tenant, target_admin.id)

    result = AdminUserOut.model_validate(target_admin)
    db.delete(target_admin)
    db.commit()
    log_action(
        db, tenant, admin, "admin.deleted",
        target=f"admin:{admin_id}", details=f"email={result.email}",
    )
    return result


@router.get("/audit-log", response_model=list[AuditLogOut])
def get_audit_log(
    tenant_slug: str,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(require_owner),
):
    tenant = get_tenant(tenant_slug, db)
    return (
        db.query(AuditLog)
        .filter(AuditLog.tenant_id == tenant.id)
        .order_by(AuditLog.created_at.desc())
        .limit(200)
        .all()
    )
