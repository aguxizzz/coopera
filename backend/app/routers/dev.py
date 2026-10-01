"""Endpoints for Coopera platform staff (devs): create cooperativas and manage
their admins across tenants. Cross-tenant data access (socios, facturas,
config, import) reuses the existing `/api/t/{slug}/admin/...` endpoints —
`get_current_admin` accepts a platform token for any tenant_slug."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import (
    create_platform_token,
    get_current_platform_user,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models import AdminUser, Member, PlatformUser, Tenant
from app.rate_limit import limiter
from app.schemas import (
    AdminCreate,
    AdminPasswordReset,
    AdminUserOut,
    PlatformLogin,
    TenantCreate,
    TenantSettingsOut,
    TenantSummary,
    TokenResponse,
)
from app.services.audit import log_action

router = APIRouter(prefix="/api/dev", tags=["dev"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(request: Request, payload: PlatformLogin, db: Session = Depends(get_db)):
    user = db.query(PlatformUser).filter(PlatformUser.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas")
    token = create_platform_token(user.id)
    return TokenResponse(access_token=token)


@router.get("/tenants", response_model=list[TenantSummary])
def list_tenants(
    db: Session = Depends(get_db),
    _platform_user: PlatformUser = Depends(get_current_platform_user),
):
    tenants = db.query(Tenant).order_by(Tenant.created_at.desc()).all()
    rows = []
    for t in tenants:
        admin_count = db.query(func.count(AdminUser.id)).filter(AdminUser.tenant_id == t.id).scalar()
        member_count = db.query(func.count(Member.id)).filter(Member.tenant_id == t.id).scalar()
        rows.append(
            TenantSummary(
                id=t.id,
                slug=t.slug,
                name=t.name,
                admin_count=admin_count or 0,
                member_count=member_count or 0,
                created_at=t.created_at,
            )
        )
    return rows


@router.post("/tenants", response_model=TenantSettingsOut)
def create_tenant(
    payload: TenantCreate,
    db: Session = Depends(get_db),
    _platform_user: PlatformUser = Depends(get_current_platform_user),
):
    if db.query(Tenant).filter(Tenant.slug == payload.slug).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ya existe una cooperativa con ese slug")

    tenant = Tenant(
        slug=payload.slug,
        name=payload.name,
        mp_alias=payload.mp_alias,
        mp_cbu=payload.mp_cbu,
        mp_titular=payload.mp_titular,
        primary_color=payload.primary_color,
    )
    db.add(tenant)
    db.flush()

    db.add(
        AdminUser(
            tenant_id=tenant.id,
            email=payload.admin_email,
            hashed_password=hash_password(payload.admin_password),
            role="owner",
        )
    )
    db.commit()
    db.refresh(tenant)
    return tenant


@router.get("/tenants/{tenant_slug}", response_model=TenantSettingsOut)
def get_tenant_detail(
    tenant_slug: str,
    db: Session = Depends(get_db),
    _platform_user: PlatformUser = Depends(get_current_platform_user),
):
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cooperativa no encontrada")
    return tenant


@router.get("/tenants/{tenant_slug}/admins", response_model=list[AdminUserOut])
def list_tenant_admins(
    tenant_slug: str,
    db: Session = Depends(get_db),
    _platform_user: PlatformUser = Depends(get_current_platform_user),
):
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cooperativa no encontrada")
    return db.query(AdminUser).filter(AdminUser.tenant_id == tenant.id).order_by(AdminUser.email).all()


@router.post("/tenants/{tenant_slug}/admins", response_model=AdminUserOut)
def create_tenant_admin(
    tenant_slug: str,
    payload: AdminCreate,
    db: Session = Depends(get_db),
    platform_user: PlatformUser = Depends(get_current_platform_user),
):
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cooperativa no encontrada")
    if db.query(AdminUser).filter(AdminUser.tenant_id == tenant.id, AdminUser.email == payload.email).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ya existe un admin con ese email en esta cooperativa")

    admin = AdminUser(
        tenant_id=tenant.id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    log_action(
        db, tenant, platform_user, "admin.created",
        target=f"admin:{admin.id}", details=f"email={admin.email}, role={admin.role}",
        actor_type="platform",
    )
    return admin


@router.post("/tenants/{tenant_slug}/admins/{admin_id}/reset-password", response_model=AdminUserOut)
def reset_admin_password(
    tenant_slug: str,
    admin_id: int,
    payload: AdminPasswordReset,
    db: Session = Depends(get_db),
    platform_user: PlatformUser = Depends(get_current_platform_user),
):
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cooperativa no encontrada")
    admin = (
        db.query(AdminUser)
        .filter(AdminUser.id == admin_id, AdminUser.tenant_id == tenant.id)
        .first()
    )
    if admin is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Admin no encontrado")
    admin.hashed_password = hash_password(payload.password)
    db.commit()
    db.refresh(admin)
    log_action(
        db, tenant, platform_user, "admin.password_reset",
        target=f"admin:{admin.id}", actor_type="platform",
    )
    return admin


@router.delete("/tenants/{tenant_slug}/admins/{admin_id}", response_model=AdminUserOut)
def delete_tenant_admin(
    tenant_slug: str,
    admin_id: int,
    db: Session = Depends(get_db),
    platform_user: PlatformUser = Depends(get_current_platform_user),
):
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cooperativa no encontrada")
    admin = (
        db.query(AdminUser)
        .filter(AdminUser.id == admin_id, AdminUser.tenant_id == tenant.id)
        .first()
    )
    if admin is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Admin no encontrado")
    result = AdminUserOut.model_validate(admin)
    db.delete(admin)
    db.commit()
    log_action(
        db, tenant, platform_user, "admin.deleted",
        target=f"admin:{admin_id}", details=f"email={result.email}", actor_type="platform",
    )
    return result
