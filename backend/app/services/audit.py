"""Audit trail for sensitive tenant actions. Call `log_action` right after the
mutation it describes commits successfully."""

from sqlalchemy.orm import Session

from app.models import AuditLog, Tenant


def log_action(
    db: Session,
    tenant: Tenant,
    actor,
    action: str,
    target: str | None = None,
    details: str | None = None,
    actor_type: str | None = None,
) -> None:
    entry = AuditLog(
        tenant_id=tenant.id,
        actor_type=actor_type or ("platform" if getattr(actor, "is_platform", False) else "admin"),
        actor_id=actor.id,
        actor_email=actor.email,
        action=action,
        target=target,
        details=details,
    )
    db.add(entry)
    db.commit()
