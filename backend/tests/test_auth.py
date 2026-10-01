import datetime as dt

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt

from app.auth import (
    PlatformActor,
    create_access_token,
    create_platform_token,
    get_current_admin,
    get_current_platform_user,
    hash_password,
    verify_password,
)
from app.config import settings


def test_hash_password_roundtrip():
    hashed = hash_password("my-secret")
    assert hashed != "my-secret"
    assert verify_password("my-secret", hashed)
    assert not verify_password("wrong", hashed)


def test_create_access_token_payload():
    token = create_access_token(admin_id=7, tenant_id=3)
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    assert payload["sub"] == "7"
    assert payload["tenant_id"] == 3
    assert "platform" not in payload


def test_create_platform_token_payload():
    token = create_platform_token(platform_user_id=42)
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    assert payload["sub"] == "42"
    assert payload["platform"] is True


def test_get_current_admin_rejects_missing_credentials(db_session, tenant):
    with pytest.raises(HTTPException) as exc_info:
        get_current_admin(tenant.slug, credentials=None, db=db_session)
    assert exc_info.value.status_code == 401


def test_get_current_admin_rejects_invalid_token(db_session, tenant):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="garbage")
    with pytest.raises(HTTPException) as exc_info:
        get_current_admin(tenant.slug, credentials=creds, db=db_session)
    assert exc_info.value.status_code == 401


def test_get_current_admin_rejects_token_for_other_tenant(db_session, tenant, admin):
    other_token = create_access_token(admin.id, tenant_id=admin.tenant_id + 999)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=other_token)
    with pytest.raises(HTTPException) as exc_info:
        get_current_admin(tenant.slug, credentials=creds, db=db_session)
    assert exc_info.value.status_code == 403


def test_get_current_admin_accepts_valid_token(db_session, tenant, admin, admin_token):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=admin_token)
    resolved = get_current_admin(tenant.slug, credentials=creds, db=db_session)
    assert resolved.id == admin.id


def test_get_current_admin_accepts_platform_token_as_platform_actor(
    db_session, tenant, platform_user, platform_token
):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=platform_token)
    resolved = get_current_admin(tenant.slug, credentials=creds, db=db_session)
    assert isinstance(resolved, PlatformActor)
    assert resolved.tenant_id == tenant.id
    assert resolved.is_platform is True


def test_get_current_platform_user_rejects_admin_token(db_session, admin_token):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=admin_token)
    with pytest.raises(HTTPException) as exc_info:
        get_current_platform_user(credentials=creds, db=db_session)
    assert exc_info.value.status_code == 403


def test_decode_rejects_expired_token(db_session, tenant, admin):
    expired = jwt.encode(
        {"sub": str(admin.id), "tenant_id": admin.tenant_id, "exp": dt.datetime.utcnow() - dt.timedelta(minutes=1)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=expired)
    with pytest.raises(HTTPException) as exc_info:
        get_current_admin(tenant.slug, credentials=creds, db=db_session)
    assert exc_info.value.status_code == 401
