import datetime as dt

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_admin, hash_password, require_owner, verify_password
from app.config import settings
from app.database import get_db
from app.deps import get_tenant
from app.models import (
    AdminUser,
    AuditLog,
    Gestor,
    Invoice,
    Member,
    Meter,
    PdfImportJob,
    Reading,
    Route,
    RouteRun,
    Tenant,
)
from app.rate_limit import limiter
from app.services import routes as route_service
from app.schemas import (
    AdminCreate,
    AdminLogin,
    AdminPasswordReset,
    AdminRoleUpdate,
    AdminUserOut,
    AuditLogOut,
    DeleteMembersRequest,
    DeleteMembersResult,
    GestorActivoUpdate,
    GestorCreate,
    GestorOut,
    GestorQrAdminStatusOut,
    GestorQrStartOut,
    GestorSharedPasswordUpdate,
    HelipagosConnectRequest,
    HelipagosStatusOut,
    ImportResult,
    InvoiceOut,
    MacroclickConnectRequest,
    MacroclickStatusOut,
    MemberRow,
    MeterCreate,
    RouteAutoGenerate,
    RouteCreate,
    RouteOut,
    RouteUpdate,
    RunOut,
    MeterOut,
    MpConnectUrlOut,
    MpStatusOut,
    PdfImportJobOut,
    ReadingOut,
    TenantSettingsOut,
    TenantSettingsUpdate,
    TokenResponse,
    UpdateInvoicePagado,
)
from app.services.audit import log_action
from app.services.importer import ImportError_, import_spreadsheet
from app.services.helipagos import disconnect_tenant as disconnect_helipagos_tenant
from app.services.helipagos import save_credentials as save_helipagos_credentials
from app.services.macroclick import disconnect_tenant as disconnect_macroclick_tenant
from app.services.macroclick import save_credentials as save_macroclick_credentials
from app.services.mercadopago import MercadoPagoError, build_authorize_url, disconnect_tenant
from app.services.qr_login import (
    approve as approve_qr_session,
    deny as deny_qr_session,
    get_qr_session,
    resolve_status as resolve_qr_status,
    start_session as start_qr_session,
)
from app.services.pdf_importer import run_pdf_import_job
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


@router.post("/import-pdf", response_model=PdfImportJobOut)
async def import_members_pdf(
    tenant_slug: str,
    background_tasks: BackgroundTasks,
    period_year: int = Form(...),
    period_month: int = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Import socios from one or more PDFs (one page = one socio), using the
    extraction profile a Coopera dev configured for this cooperativa via the
    /api/dev panel. Runs in the background — poll /import-pdf/status/{id}."""
    tenant = get_tenant(tenant_slug, db)

    contents = [(f.filename or "boleta.pdf", await f.read()) for f in files]

    job = PdfImportJob(tenant_id=tenant.id, period_year=period_year, period_month=period_month)
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(run_pdf_import_job, job.id, contents)
    return job


@router.get("/import-pdf/status/{job_id}", response_model=PdfImportJobOut)
def import_pdf_status(
    tenant_slug: str,
    job_id: int,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    job = db.query(PdfImportJob).filter(PdfImportJob.id == job_id, PdfImportJob.tenant_id == tenant.id).first()
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job no encontrado")
    return job


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
    member = db.query(Member).filter(Member.id == invoice.member_id).first()
    log_action(
        db, tenant, _admin, "invoice.pagado_updated",
        target=f"invoice:{invoice.id}",
        details=(
            f"pagado={payload.pagado} | socio={member.nombre if member else '?'} | "
            f"periodo={invoice.period_month}/{invoice.period_year}"
        ),
    )
    return invoice


@router.post("/members/{member_id}/mark-oldest-invoice-paid", response_model=InvoiceOut)
def mark_oldest_invoice_paid(
    tenant_slug: str,
    member_id: int,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Atajo para pagos registrados a mano (efectivo, transferencia): marca
    pagada la factura impaga más vieja del socio, para no obligar al admin a
    entrar al detalle y elegir el período cuando hay una sola deuda obvia."""
    tenant = get_tenant(tenant_slug, db)
    member = (
        db.query(Member)
        .filter(Member.id == member_id, Member.tenant_id == tenant.id)
        .first()
    )
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Socio no encontrado")
    invoice = (
        db.query(Invoice)
        .filter(Invoice.member_id == member.id, Invoice.pagado.is_(False))
        .order_by(Invoice.period_year, Invoice.period_month)
        .first()
    )
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El socio no tiene facturas impagas")
    invoice.pagado = True
    db.commit()
    db.refresh(invoice)
    log_action(
        db, tenant, _admin, "invoice.pagado_updated",
        target=f"invoice:{invoice.id}",
        details=(
            f"pagado=True (atajo: factura más vieja impaga) | socio={member.nombre} | "
            f"periodo={invoice.period_month}/{invoice.period_year}"
        ),
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


@router.get("/helipagos/status", response_model=HelipagosStatusOut)
def helipagos_status(
    tenant_slug: str,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    return HelipagosStatusOut(
        connected=bool(tenant.helipagos_token), environment=tenant.helipagos_environment
    )


@router.put("/helipagos", response_model=HelipagosStatusOut)
def helipagos_connect(
    tenant_slug: str,
    payload: HelipagosConnectRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_owner),
):
    tenant = get_tenant(tenant_slug, db)
    save_helipagos_credentials(db, tenant, payload.token, payload.webhook_apikey, payload.environment)
    log_action(db, tenant, admin, "helipagos.connected")
    return HelipagosStatusOut(connected=True, environment=tenant.helipagos_environment)


@router.delete("/helipagos", response_model=HelipagosStatusOut)
def helipagos_disconnect(
    tenant_slug: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_owner),
):
    tenant = get_tenant(tenant_slug, db)
    disconnect_helipagos_tenant(db, tenant)
    log_action(db, tenant, admin, "helipagos.disconnected")
    return HelipagosStatusOut(connected=False, environment="sandbox")


@router.get("/macroclick/status", response_model=MacroclickStatusOut)
def macroclick_status(
    tenant_slug: str,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    return MacroclickStatusOut(
        connected=bool(tenant.macroclick_comercio_id), environment=tenant.macroclick_environment
    )


@router.put("/macroclick", response_model=MacroclickStatusOut)
def macroclick_connect(
    tenant_slug: str,
    payload: MacroclickConnectRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_owner),
):
    tenant = get_tenant(tenant_slug, db)
    save_macroclick_credentials(
        db, tenant, payload.comercio_id, payload.sucursal, payload.secret_key, payload.environment
    )
    log_action(db, tenant, admin, "macroclick.connected")
    return MacroclickStatusOut(connected=True, environment=tenant.macroclick_environment)


@router.delete("/macroclick", response_model=MacroclickStatusOut)
def macroclick_disconnect(
    tenant_slug: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_owner),
):
    tenant = get_tenant(tenant_slug, db)
    disconnect_macroclick_tenant(db, tenant)
    log_action(db, tenant, admin, "macroclick.disconnected")
    return MacroclickStatusOut(connected=False, environment="sandbox")


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


# --- Gestores de consumos (lectores de medidores) --------------------------


@router.get("/gestores", response_model=list[GestorOut])
def list_gestores(
    tenant_slug: str,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    return db.query(Gestor).filter(Gestor.tenant_id == tenant.id).order_by(Gestor.nombre).all()


@router.post("/gestores", response_model=GestorOut)
def create_gestor(
    tenant_slug: str,
    payload: GestorCreate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    if db.query(Gestor).filter(Gestor.tenant_id == tenant.id, Gestor.email == payload.email).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ya existe un gestor con ese email")

    gestor = Gestor(
        tenant_id=tenant.id,
        nombre=payload.nombre,
        email=payload.email,
    )
    db.add(gestor)
    db.commit()
    db.refresh(gestor)
    log_action(db, tenant, admin, "gestor.created", target=f"gestor:{gestor.id}", details=f"email={gestor.email}")
    return gestor


@router.put("/gestores/shared-password", status_code=status.HTTP_204_NO_CONTENT)
def set_gestor_shared_password(
    tenant_slug: str,
    payload: GestorSharedPasswordUpdate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_owner),
):
    """Sets (or rotates) the single password every gestor device uses to log
    in — see app/routers/gestor.py's /device-login. Owner-only since it's
    effectively a shared credential for the whole field team."""
    tenant = get_tenant(tenant_slug, db)
    tenant.gestor_shared_password_hash = hash_password(payload.password)
    db.commit()
    log_action(db, tenant, admin, "gestor.shared_password_updated")


@router.patch("/gestores/{gestor_id}/activo", response_model=GestorOut)
def update_gestor_activo(
    tenant_slug: str,
    gestor_id: int,
    payload: GestorActivoUpdate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    gestor = db.query(Gestor).filter(Gestor.id == gestor_id, Gestor.tenant_id == tenant.id).first()
    if gestor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gestor no encontrado")
    gestor.activo = payload.activo
    db.commit()
    db.refresh(gestor)
    log_action(db, tenant, admin, "gestor.activo_updated", target=f"gestor:{gestor.id}", details=f"activo={payload.activo}")
    return gestor


# --- QR login: alternative to typing the shared password -------------------
# See app/services/qr_login.py for the full handshake and why the explicit
# approve/deny step below matters.


@router.post("/gestor-qr/start", response_model=GestorQrStartOut)
@limiter.limit("10/minute")
def start_gestor_qr(
    request: Request,
    tenant_slug: str,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    session = start_qr_session(db, tenant)
    return GestorQrStartOut(code=session.code, expires_at=session.expires_at)


@router.get("/gestor-qr/{code}/status", response_model=GestorQrAdminStatusOut)
def gestor_qr_status(
    tenant_slug: str,
    code: str,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    session = get_qr_session(db, tenant.id, code)
    return GestorQrAdminStatusOut(status=resolve_qr_status(db, session), expires_at=session.expires_at)


@router.post("/gestor-qr/{code}/approve", response_model=GestorQrAdminStatusOut)
def approve_gestor_qr(
    tenant_slug: str,
    code: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """Only valid once a device has claimed the code — see
    app/services/qr_login.py. This is the human-in-the-loop step: the admin
    is confirming "yes, that's my gestor's phone in front of me right now"."""
    tenant = get_tenant(tenant_slug, db)
    session = get_qr_session(db, tenant.id, code)
    if resolve_qr_status(db, session) != "claimed":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "El código no tiene un dispositivo esperando confirmación"
        )
    approve_qr_session(db, session)
    log_action(db, tenant, admin, "gestor.qr_login_approved")
    return GestorQrAdminStatusOut(status=session.status, expires_at=session.expires_at)


@router.post("/gestor-qr/{code}/deny", response_model=GestorQrAdminStatusOut)
def deny_gestor_qr(
    tenant_slug: str,
    code: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    session = get_qr_session(db, tenant.id, code)
    deny_qr_session(db, session)
    log_action(db, tenant, admin, "gestor.qr_login_denied")
    return GestorQrAdminStatusOut(status=session.status, expires_at=session.expires_at)


# --- Medidores y lecturas ---------------------------------------------------


@router.get("/meters", response_model=list[MeterOut])
def list_meters(
    tenant_slug: str,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    meters = db.query(Meter).filter(Meter.tenant_id == tenant.id).order_by(Meter.codigo).all()

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


@router.post("/meters", response_model=MeterOut)
def create_meter(
    tenant_slug: str,
    payload: MeterCreate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    member = db.query(Member).filter(Member.id == payload.member_id, Member.tenant_id == tenant.id).first()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Socio no encontrado")
    if db.query(Meter).filter(Meter.tenant_id == tenant.id, Meter.codigo == payload.codigo).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ya existe un medidor con ese código")

    meter = Meter(
        tenant_id=tenant.id,
        member_id=member.id,
        codigo=payload.codigo,
        tipo=payload.tipo,
        direccion=payload.direccion,
        unidad=payload.unidad,
    )
    db.add(meter)
    db.commit()
    db.refresh(meter)
    log_action(db, tenant, admin, "meter.created", target=f"meter:{meter.id}", details=f"codigo={meter.codigo}")
    return MeterOut(
        id=meter.id,
        codigo=meter.codigo,
        tipo=meter.tipo,
        direccion=meter.direccion,
        unidad=meter.unidad,
        activo=meter.activo,
        member_id=meter.member_id,
        numero_socio=member.numero_socio,
        nombre_socio=member.nombre,
        ultima_lectura=None,
        ultima_lectura_fecha=None,
    )


@router.get("/meters/{meter_id}/readings", response_model=list[ReadingOut])
def list_meter_readings(
    tenant_slug: str,
    meter_id: int,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    meter = db.query(Meter).filter(Meter.id == meter_id, Meter.tenant_id == tenant.id).first()
    if meter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Medidor no encontrado")
    return (
        db.query(Reading)
        .filter(Reading.meter_id == meter.id)
        .order_by(Reading.created_at.desc())
        .all()
    )


# --- Rutas de lectura --------------------------------------------------------


@router.get("/routes", response_model=list[RouteOut])
def list_routes(
    tenant_slug: str,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    routes = db.query(Route).filter(Route.tenant_id == tenant.id).order_by(Route.nombre).all()
    return [route_service.route_out(r) for r in routes]


@router.post("/routes", response_model=RouteOut)
def create_route(
    tenant_slug: str,
    payload: RouteCreate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    route = route_service.create_route(db, tenant.id, payload.nombre, payload.meter_ids, payload.gestor_id)
    log_action(db, tenant, admin, "route.created", target=f"route:{route.id}", details=f"nombre={route.nombre}")
    return route_service.route_out(route)


@router.post("/routes/auto-generate", response_model=list[RouteOut])
def auto_generate_routes(
    tenant_slug: str,
    payload: RouteAutoGenerate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """Proposes (preview=true) or creates routes covering the active meters,
    grouped by proximity. See app/services/routes.py."""
    tenant = get_tenant(tenant_slug, db)
    created = route_service.auto_generate(db, tenant.id, **payload.model_dump())
    if not payload.preview:
        log_action(db, tenant, admin, "route.auto_generated", details=f"rutas={len(created)}")
    return created


@router.get("/routes/{route_id}", response_model=RouteOut)
def get_route(
    tenant_slug: str,
    route_id: int,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    return route_service.route_out(route_service.get_route(db, tenant.id, route_id))


@router.put("/routes/{route_id}", response_model=RouteOut)
def update_route(
    tenant_slug: str,
    route_id: int,
    payload: RouteUpdate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    route = route_service.get_route(db, tenant.id, route_id)
    if payload.nombre is not None:
        route.nombre = payload.nombre
    if payload.activo is not None:
        route.activo = payload.activo
    if "gestor_id" in payload.model_fields_set:
        route_service.check_gestor(db, tenant.id, payload.gestor_id)
        route.gestor_id = payload.gestor_id
    if payload.meter_ids is not None:
        route_service.set_stops(db, route, payload.meter_ids)
    db.commit()
    db.refresh(route)
    log_action(db, tenant, admin, "route.updated", target=f"route:{route.id}")
    return route_service.route_out(route)


@router.delete("/routes/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_route(
    tenant_slug: str,
    route_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    route = route_service.get_route(db, tenant.id, route_id)
    if db.query(RouteRun.id).filter(RouteRun.route_id == route.id).first():
        # Past recorridos keep pointing at it as history; deactivate instead.
        raise HTTPException(
            status.HTTP_409_CONFLICT, "La ruta ya tiene recorridos realizados; desactivala en lugar de borrarla"
        )
    db.delete(route)
    db.commit()
    log_action(db, tenant, admin, "route.deleted", target=f"route:{route_id}")


@router.get("/route-runs", response_model=list[RunOut])
def list_route_runs(
    tenant_slug: str,
    run_status: str | None = None,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Progress of recorridos (e.g. ?run_status=en_curso to see who's out
    reading right now)."""
    tenant = get_tenant(tenant_slug, db)
    q = db.query(RouteRun).filter(RouteRun.tenant_id == tenant.id)
    if run_status:
        q = q.filter(RouteRun.status == run_status)
    runs = q.order_by(RouteRun.started_at.desc()).limit(100).all()
    return [route_service.run_out(db, r) for r in runs]


@router.get("/route-runs/{run_id}", response_model=RunOut)
def get_route_run(
    tenant_slug: str,
    run_id: int,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    tenant = get_tenant(tenant_slug, db)
    return route_service.run_out(db, route_service.get_run(db, tenant.id, run_id), include_stops=True)
