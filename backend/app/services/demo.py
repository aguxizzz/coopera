"""Reset de la cooperativa demo (valle-verde): borra lo que los gestores
cargaron jugando con la app y vuelve a dejar los datos iniciales del seed."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    Gestor,
    ImportBatch,
    Invoice,
    Member,
    Meter,
    PdfImportJob,
    Reading,
    Route,
    RouteRun,
    RouteRunStop,
    RouteStop,
    ServiceCut,
    Tenant,
)
from app.services.demo_seed import TENANTS, seed_tenant

DEMO_SLUG = "valle-verde"


def is_demo(tenant: Tenant) -> bool:
    return tenant.slug == DEMO_SLUG


def reset_demo(db: Session, tenant: Tenant) -> None:
    """Vuelve los datos de la demo a su estado inicial. Los gestores y sus
    sesiones se conservan para que quien dispara el reset no quede afuera."""
    tid = tenant.id
    runs = select(RouteRun.id).where(RouteRun.tenant_id == tid)
    routes = select(Route.id).where(Route.tenant_id == tid)
    db.execute(delete(RouteRunStop).where(RouteRunStop.run_id.in_(runs)))
    db.execute(delete(RouteRun).where(RouteRun.tenant_id == tid))
    db.execute(delete(RouteStop).where(RouteStop.route_id.in_(routes)))
    db.execute(delete(Route).where(Route.tenant_id == tid))
    db.execute(delete(ServiceCut).where(ServiceCut.tenant_id == tid))
    db.execute(delete(Reading).where(Reading.tenant_id == tid))
    db.execute(delete(Meter).where(Meter.tenant_id == tid))
    db.execute(delete(Invoice).where(Invoice.tenant_id == tid))
    db.execute(delete(PdfImportJob).where(PdfImportJob.tenant_id == tid))
    db.execute(delete(ImportBatch).where(ImportBatch.tenant_id == tid))
    db.execute(delete(Member).where(Member.tenant_id == tid))
    db.flush()

    seed = next(t for t in TENANTS if t["slug"] == DEMO_SLUG)
    seed_tenant(db, seed)

    # Gestores del seed: vuelven a su estado (activo/inactivo) original.
    activos = {seed["gestor_email"]: True, **{email: activo for _, email, activo in seed["gestores_extra"]}}
    for gestor in db.query(Gestor).filter(Gestor.tenant_id == tid, Gestor.email.in_(activos)):
        gestor.activo = activos[gestor.email]
    db.commit()
