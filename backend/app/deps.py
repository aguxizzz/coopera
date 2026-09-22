from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Tenant


def get_tenant(tenant_slug: str, db: Session = Depends(get_db)) -> Tenant:
    """Resolves the tenant from the URL path today. In production this is where
    we'd instead resolve from the Host header once each cooperativa has its own
    domain, without touching any of the route handlers below."""
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cooperativa no encontrada")
    return tenant
