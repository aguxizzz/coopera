from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_tenant
from app.models import Invoice, Member, Tenant
from app.schemas import InvoiceOut, MemberAccountOut, MemberLookupRequest, TenantPublic
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
def lookup_member(tenant_slug: str, payload: MemberLookupRequest, db: Session = Depends(get_db)):
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
    )


@router.get("/boleta.pdf")
def download_boleta(
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
