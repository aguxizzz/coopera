import datetime as dt

import httpx
import pytest
from jose import jwt

from app.config import settings
from app.services import mercadopago as mp


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text or str(json_data)

    def json(self):
        return self._json


def test_build_and_read_state_roundtrip():
    state = mp.build_state("coopera-test")
    assert mp.read_state(state) == "coopera-test"


def test_read_state_rejects_garbage():
    with pytest.raises(mp.MercadoPagoError):
        mp.read_state("not-a-real-token")


def test_read_state_rejects_expired():
    expired = jwt.encode(
        {"aud": mp.STATE_AUDIENCE, "tenant_slug": "coopera-test", "exp": dt.datetime.utcnow() - dt.timedelta(minutes=1)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(mp.MercadoPagoError):
        mp.read_state(expired)


def test_build_authorize_url_requires_configuration(monkeypatch):
    monkeypatch.setattr(settings, "mp_client_id", None)
    monkeypatch.setattr(settings, "mp_client_secret", None)
    with pytest.raises(mp.MercadoPagoError):
        mp.build_authorize_url("coopera-test")


def test_build_authorize_url_includes_signed_state(monkeypatch):
    monkeypatch.setattr(settings, "mp_client_id", "client-id")
    monkeypatch.setattr(settings, "mp_client_secret", "client-secret")
    url = mp.build_authorize_url("coopera-test")
    assert url.startswith(mp.MP_AUTHORIZE_URL)
    assert "state=" in url


def test_encrypt_decrypt_roundtrip():
    secret = "super-secret-token"
    encrypted = mp._encrypt(secret)
    assert encrypted != secret
    assert mp._decrypt(encrypted) == secret


def test_connect_tenant_saves_tokens(monkeypatch, db_session, tenant):
    def fake_post(url, json=None, timeout=None):
        return FakeResponse(
            200,
            {
                "user_id": 555,
                "access_token": "access-abc",
                "refresh_token": "refresh-abc",
                "public_key": "pub-abc",
                "expires_in": 21600,
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    mp.connect_tenant(db_session, tenant, "auth-code")

    assert tenant.mp_user_id == "555"
    assert mp._decrypt(tenant.mp_access_token) == "access-abc"
    assert mp._decrypt(tenant.mp_refresh_token) == "refresh-abc"


def test_connect_tenant_raises_on_error_response(monkeypatch, db_session, tenant):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse(400, text="bad code"))
    with pytest.raises(mp.MercadoPagoError):
        mp.connect_tenant(db_session, tenant, "bad-code")


def test_disconnect_tenant_clears_fields(db_session, tenant):
    tenant.mp_access_token = "x"
    tenant.mp_refresh_token = "y"
    tenant.mp_user_id = "1"
    db_session.commit()

    mp.disconnect_tenant(db_session, tenant)

    assert tenant.mp_access_token is None
    assert tenant.mp_refresh_token is None
    assert tenant.mp_user_id is None


def test_get_access_token_requires_connection(db_session, tenant):
    with pytest.raises(mp.MercadoPagoError):
        mp.get_access_token(db_session, tenant)


def test_get_access_token_returns_cached_when_not_expiring(db_session, tenant):
    tenant.mp_access_token = mp._encrypt("still-valid")
    tenant.mp_token_expires_at = dt.datetime.utcnow() + dt.timedelta(hours=2)
    db_session.commit()

    assert mp.get_access_token(db_session, tenant) == "still-valid"


def test_get_access_token_refreshes_when_near_expiry(monkeypatch, db_session, tenant):
    tenant.mp_access_token = mp._encrypt("old-token")
    tenant.mp_refresh_token = mp._encrypt("refresh-token")
    tenant.mp_token_expires_at = dt.datetime.utcnow() + dt.timedelta(minutes=1)
    db_session.commit()

    def fake_post(url, json=None, timeout=None):
        return FakeResponse(
            200,
            {
                "user_id": 555,
                "access_token": "new-token",
                "refresh_token": "new-refresh",
                "expires_in": 21600,
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    token = mp.get_access_token(db_session, tenant)
    assert token == "new-token"


def test_create_preference_success(monkeypatch, db_session, tenant, member, invoice):
    tenant.mp_access_token = mp._encrypt("access-token")
    tenant.mp_token_expires_at = dt.datetime.utcnow() + dt.timedelta(hours=2)
    db_session.commit()

    def fake_post(url, headers=None, json=None, timeout=None):
        assert headers["Authorization"] == "Bearer access-token"
        assert json["external_reference"] == str(invoice.id)
        return FakeResponse(201, {"id": "pref-123", "init_point": "https://mp.test/checkout/pref-123"})

    monkeypatch.setattr(httpx, "post", fake_post)
    pref = mp.create_preference(db_session, tenant, member, invoice)

    assert pref["init_point"] == "https://mp.test/checkout/pref-123"
    assert invoice.mp_preference_id == "pref-123"


def test_create_preference_raises_on_failure(monkeypatch, db_session, tenant, member, invoice):
    tenant.mp_access_token = mp._encrypt("access-token")
    tenant.mp_token_expires_at = dt.datetime.utcnow() + dt.timedelta(hours=2)
    db_session.commit()

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse(400, text="boom"))
    with pytest.raises(mp.MercadoPagoError):
        mp.create_preference(db_session, tenant, member, invoice)


def test_process_webhook_payment_marks_invoice_paid(monkeypatch, db_session, tenant, member, invoice):
    tenant.mp_access_token = mp._encrypt("access-token")
    tenant.mp_token_expires_at = dt.datetime.utcnow() + dt.timedelta(hours=2)
    db_session.commit()

    def fake_get(url, headers=None, timeout=None):
        return FakeResponse(
            200, {"id": 999, "status": "approved", "external_reference": str(invoice.id)}
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    result = mp.process_webhook_payment(db_session, tenant, "999")

    assert result.id == invoice.id
    assert result.pagado is True
    assert result.mp_payment_id == "999"


def test_process_webhook_payment_ignores_non_approved(monkeypatch, db_session, tenant, member, invoice):
    tenant.mp_access_token = mp._encrypt("access-token")
    tenant.mp_token_expires_at = dt.datetime.utcnow() + dt.timedelta(hours=2)
    db_session.commit()

    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **k: FakeResponse(200, {"id": 999, "status": "pending", "external_reference": str(invoice.id)}),
    )
    result = mp.process_webhook_payment(db_session, tenant, "999")
    assert result.pagado is False


def test_process_webhook_payment_unknown_reference_returns_none(monkeypatch, db_session, tenant):
    tenant.mp_access_token = mp._encrypt("access-token")
    tenant.mp_token_expires_at = dt.datetime.utcnow() + dt.timedelta(hours=2)
    db_session.commit()

    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **k: FakeResponse(200, {"id": 999, "status": "approved", "external_reference": "not-a-number"}),
    )
    assert mp.process_webhook_payment(db_session, tenant, "999") is None
