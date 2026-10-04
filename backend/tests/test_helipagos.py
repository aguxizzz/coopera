import datetime as dt

import httpx
import pytest

from app.services import helipagos as hp


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text or str(json_data)

    def json(self):
        return self._json


def test_encrypt_decrypt_roundtrip():
    secret = "super-secret-token"
    encrypted = hp._encrypt(secret)
    assert encrypted != secret
    assert hp._decrypt(encrypted) == secret


def test_base_url_sandbox_by_default(tenant):
    assert hp._base_url(tenant) == hp.HELIPAGOS_SANDBOX_BASE


def test_base_url_production(tenant):
    tenant.helipagos_environment = "production"
    assert hp._base_url(tenant) == hp.HELIPAGOS_PROD_BASE


def test_save_credentials_encrypts_and_stores(db_session, tenant):
    hp.save_credentials(db_session, tenant, "token-abc", "apikey-xyz", "production")

    assert hp._decrypt(tenant.helipagos_token) == "token-abc"
    assert hp._decrypt(tenant.helipagos_webhook_apikey) == "apikey-xyz"
    assert tenant.helipagos_environment == "production"


def test_disconnect_tenant_clears_fields(db_session, tenant):
    hp.save_credentials(db_session, tenant, "token-abc", "apikey-xyz", "production")
    hp.disconnect_tenant(db_session, tenant)

    assert tenant.helipagos_token is None
    assert tenant.helipagos_webhook_apikey is None
    assert tenant.helipagos_environment == "sandbox"


def test_create_solicitud_pago_requires_connection(db_session, tenant, member, invoice):
    with pytest.raises(hp.HelipagosError):
        hp.create_solicitud_pago(db_session, tenant, member, invoice)


def test_create_solicitud_pago_success(monkeypatch, db_session, tenant, member, invoice):
    hp.save_credentials(db_session, tenant, "token-abc", "apikey-xyz", "sandbox")

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == f"{hp.HELIPAGOS_SANDBOX_BASE}{hp.SOLICITUD_PAGO_PATH}"
        assert headers["Authorization"] == "Bearer token-abc"
        assert json["importe"] == 450000  # 4500.0 -> centavos
        assert json["referencia_externa"] == f"inv-{invoice.id}"
        return FakeResponse(
            201,
            {
                "id_sp": 1532789,
                "estado": "GENERADA",
                "checkout_url": "https://checkout.helipagos.com/checkout/abc",
                "short_url": "https://hpagos.co/2fmox",
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    data = hp.create_solicitud_pago(db_session, tenant, member, invoice)

    assert data["checkout_url"] == "https://checkout.helipagos.com/checkout/abc"
    assert invoice.helipagos_id_sp == "1532789"


def test_create_solicitud_pago_raises_on_failure(monkeypatch, db_session, tenant, member, invoice):
    hp.save_credentials(db_session, tenant, "token-abc", "apikey-xyz", "sandbox")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse(400, text="boom"))

    with pytest.raises(hp.HelipagosError):
        hp.create_solicitud_pago(db_session, tenant, member, invoice)


def test_create_solicitud_pago_reuses_pending_request(monkeypatch, db_session, tenant, member, invoice):
    hp.save_credentials(db_session, tenant, "token-abc", "apikey-xyz", "sandbox")
    invoice.helipagos_id_sp = "1527130"
    db_session.commit()

    def fake_get(url, headers=None, params=None, timeout=None):
        assert params == {"id": "1527130"}
        return FakeResponse(
            200,
            [{"id_sp": 1527130, "estado_pago": "GENERADA", "checkout_url": "https://checkout.helipagos.com/x"}],
        )

    post_called = False

    def fake_post(*a, **k):
        nonlocal post_called
        post_called = True
        return FakeResponse(201, {"id_sp": 999})

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)

    data = hp.create_solicitud_pago(db_session, tenant, member, invoice)

    assert data["checkout_url"] == "https://checkout.helipagos.com/x"
    assert post_called is False
    assert invoice.helipagos_id_sp == "1527130"


def test_create_solicitud_pago_creates_new_when_not_reusable(monkeypatch, db_session, tenant, member, invoice):
    hp.save_credentials(db_session, tenant, "token-abc", "apikey-xyz", "sandbox")
    invoice.helipagos_id_sp = "1527130"
    db_session.commit()

    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **k: FakeResponse(200, [{"id_sp": 1527130, "estado_pago": "VENCIDA"}]),
    )

    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(201, {"id_sp": 42, "checkout_url": "https://checkout.helipagos.com/new"})

    monkeypatch.setattr(httpx, "post", fake_post)

    data = hp.create_solicitud_pago(db_session, tenant, member, invoice)

    assert data["checkout_url"] == "https://checkout.helipagos.com/new"
    assert invoice.helipagos_id_sp == "42"


def test_create_solicitud_pago_defaults_fecha_vto_when_missing(monkeypatch, db_session, tenant, member, invoice):
    hp.save_credentials(db_session, tenant, "token-abc", "apikey-xyz", "sandbox")
    invoice.vencimiento = None
    db_session.commit()

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["fecha_vto"] = json["fecha_vto"]
        return FakeResponse(201, {"id_sp": 1})

    monkeypatch.setattr(httpx, "post", fake_post)
    hp.create_solicitud_pago(db_session, tenant, member, invoice)

    expected = (dt.date.today() + dt.timedelta(days=30)).isoformat()
    assert captured["fecha_vto"] == expected


def test_process_webhook_payment_marks_invoice_paid(db_session, tenant, invoice):
    invoice.helipagos_id_sp = "26"
    db_session.commit()

    result = hp.process_webhook_payment(
        db_session, tenant, {"id_sp": 26, "estado": "PROCESADA", "referencia_externa": "inv-1"}
    )

    assert result.id == invoice.id
    assert result.pagado is True


def test_process_webhook_payment_acreditada_also_marks_paid(db_session, tenant, invoice):
    invoice.helipagos_id_sp = "26"
    db_session.commit()

    result = hp.process_webhook_payment(db_session, tenant, {"id_sp": 26, "estado": "ACREDITADA"})
    assert result.pagado is True


def test_process_webhook_payment_ignores_other_states(db_session, tenant, invoice):
    invoice.helipagos_id_sp = "26"
    db_session.commit()

    result = hp.process_webhook_payment(db_session, tenant, {"id_sp": 26, "estado": "VENCIDA"})
    assert result.pagado is False


def test_process_webhook_payment_unknown_id_sp_returns_none(db_session, tenant, invoice):
    result = hp.process_webhook_payment(db_session, tenant, {"id_sp": 99999, "estado": "PROCESADA"})
    assert result is None
