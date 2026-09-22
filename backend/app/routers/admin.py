from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_admin, verify_password
from app.database import get_db
from app.deps import get_tenant
from app.models import AdminUser, Invoice, Member, Tenant
from app.schemas import AdminLogin, ImportResult, MemberRow, TokenResponse
from app.services.importer import ImportError_, import_spreadsheet

router = APIRouter(prefix="/api/t/{tenant_slug}/admin", tags=["admin"])


@router.post("/login", response_model=TokenResponse)
def login(tenant_slug: str, payload: AdminLogin, db: Session = Depends(get_db)):
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
                numero_socio=m.numero_socio,
                nombre=m.nombre,
                identificador=m.identificador,
                saldo_total=float(saldo or 0),
            )
        )
    return rows
