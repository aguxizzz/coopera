"""Backend for the gestor "scan to log in" flow: an admin generates a QR in
the panel, a gestor's phone scans it, and the admin must explicitly approve
that specific scan before the phone receives a device_token (see
app/routers/gestor.py and app/routers/admin.py's /gestor-qr endpoints, and
mobile/src/app/qr-login.tsx).

The explicit approval step is the whole point: without it, anyone who glimpses
or photographs the QR on an admin's screen could scan it and log in as a
gestor on their own device. Requiring a human to click "confirm" while
looking at the request closes that gap, the same way a smart-TV pairing code
does."""

import datetime as dt
import secrets

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.auth import create_device_token
from app.config import settings
from app.models import GestorQrSession, Tenant

_CODE_BYTES = 24


def start_session(db: Session, tenant: Tenant) -> GestorQrSession:
    session = GestorQrSession(
        tenant_id=tenant.id,
        code=secrets.token_urlsafe(_CODE_BYTES),
        status="pending",
        expires_at=dt.datetime.utcnow() + dt.timedelta(minutes=settings.gestor_qr_expire_minutes),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_qr_session(db: Session, tenant_id: int, code: str) -> GestorQrSession:
    session = (
        db.query(GestorQrSession)
        .filter(GestorQrSession.tenant_id == tenant_id, GestorQrSession.code == code)
        .first()
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Código QR inválido")
    return session


def resolve_status(db: Session, session: GestorQrSession) -> str:
    """Materializes `expired` once the window passes, persisting it so the
    admin's status poll and the gestor app's poll always agree."""
    if session.status in ("pending", "claimed") and dt.datetime.utcnow() > session.expires_at:
        session.status = "expired"
        db.add(session)
        db.commit()
    return session.status


def claim(db: Session, session: GestorQrSession) -> str:
    """Called by the gestor app right after it scans the QR. Only flips
    pending -> claimed (so the admin sees "a device wants in" and can
    approve/deny); re-claiming an already-claimed/resolved code is a no-op
    that just reports the current status."""
    status_now = resolve_status(db, session)
    if status_now == "pending":
        session.status = "claimed"
        session.expires_at = dt.datetime.utcnow() + dt.timedelta(minutes=settings.gestor_qr_expire_minutes)
        db.add(session)
        db.commit()
        status_now = "claimed"
    return status_now


def approve(db: Session, session: GestorQrSession) -> None:
    session.status = "approved"
    session.device_token = create_device_token(session.tenant_id)
    # Short window to retrieve the device_token once approved — the admin's
    # click is the authorization, not an open-ended grant.
    session.expires_at = dt.datetime.utcnow() + dt.timedelta(minutes=2)
    db.add(session)
    db.commit()


def deny(db: Session, session: GestorQrSession) -> None:
    session.status = "denied"
    db.add(session)
    db.commit()
