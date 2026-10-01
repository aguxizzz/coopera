import datetime as dt

import httpx

from app.services import mercadopago as mp


def test_oauth_callback_error_param_redirects_with_error(client):
    resp = client.get("/api/mp/oauth/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "mp=error" in resp.headers["location"]


def test_oauth_callback_missing_code_redirects_with_error(client):
    resp = client.get("/api/mp/oauth/callback", params={"state": "whatever"}, follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "mp=error" in resp.headers["location"]


def test_oauth_callback_invalid_state_redirects_with_error(client):
    resp = client.get(
        "/api/mp/oauth/callback", params={"code": "abc", "state": "garbage"}, follow_redirects=False
    )
    assert "mp=error" in resp.headers["location"]


def test_oauth_callback_unknown_tenant_redirects_with_error(client):
    state = mp.build_state("unknown-tenant-slug")
    resp = client.get(
        "/api/mp/oauth/callback", params={"code": "abc", "state": state}, follow_redirects=False
    )
    assert "mp=error" in resp.headers["location"]


def test_oauth_callback_success(client, tenant, monkeypatch):
    state = mp.build_state(tenant.slug)

    def fake_post(url, json=None, timeout=None):
        class R:
            status_code = 200

            def json(self):
                return {
                    "user_id": 1,
                    "access_token": "a",
                    "refresh_token": "b",
                    "expires_in": 21600,
                }

        return R()

    monkeypatch.setattr(httpx, "post", fake_post)
    resp = client.get(
        "/api/mp/oauth/callback", params={"code": "abc", "state": state}, follow_redirects=False
    )
    assert f"/{tenant.slug}/admin/dashboard?mp=success" in resp.headers["location"]


def test_webhook_ignores_unknown_tenant(client):
    resp = client.post("/api/t/unknown-slug/mp/webhook", json={"type": "payment", "data": {"id": "1"}})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_webhook_ignores_disconnected_tenant(client, tenant):
    resp = client.post(f"/api/t/{tenant.slug}/mp/webhook", json={"type": "payment", "data": {"id": "1"}})
    assert resp.json()["status"] == "ignored"


def test_webhook_ignores_non_payment_topic(client, db_session, tenant):
    tenant.mp_access_token = mp._encrypt("token")
    db_session.commit()

    resp = client.post(f"/api/t/{tenant.slug}/mp/webhook", json={"type": "merchant_order", "data": {"id": "1"}})
    assert resp.json()["status"] == "ignored"


def test_webhook_processes_payment(client, db_session, tenant, member, invoice, monkeypatch):
    tenant.mp_access_token = mp._encrypt("token")
    tenant.mp_token_expires_at = dt.datetime.utcnow() + dt.timedelta(hours=1)
    db_session.commit()

    def fake_get(url, headers=None, timeout=None):
        class R:
            status_code = 200

            def json(self):
                return {"id": 42, "status": "approved", "external_reference": str(invoice.id)}

        return R()

    monkeypatch.setattr(httpx, "get", fake_get)
    resp = client.post(
        f"/api/t/{tenant.slug}/mp/webhook", json={"type": "payment", "data": {"id": "42"}}
    )
    assert resp.json()["status"] == "ok"

    db_session.refresh(invoice)
    assert invoice.pagado is True
