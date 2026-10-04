from app.services import helipagos as hp


def test_webhook_ignores_unknown_tenant(client):
    resp = client.post(
        "/api/t/unknown-slug/helipagos/webhook",
        json={"id_sp": 1, "estado": "PROCESADA"},
        headers={"apikey": "whatever"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_webhook_ignores_tenant_without_helipagos(client, tenant):
    resp = client.post(
        f"/api/t/{tenant.slug}/helipagos/webhook",
        json={"id_sp": 1, "estado": "PROCESADA"},
        headers={"apikey": "whatever"},
    )
    assert resp.json()["status"] == "ignored"


def test_webhook_rejects_invalid_apikey(client, db_session, tenant, invoice):
    hp.save_credentials(db_session, tenant, "token-abc", "correct-apikey", "sandbox")
    invoice.helipagos_id_sp = "26"
    db_session.commit()

    resp = client.post(
        f"/api/t/{tenant.slug}/helipagos/webhook",
        json={"id_sp": 26, "estado": "PROCESADA"},
        headers={"apikey": "wrong-apikey"},
    )
    assert resp.json()["status"] == "ignored"

    db_session.refresh(invoice)
    assert invoice.pagado is False


def test_webhook_rejects_missing_apikey(client, db_session, tenant, invoice):
    hp.save_credentials(db_session, tenant, "token-abc", "correct-apikey", "sandbox")
    invoice.helipagos_id_sp = "26"
    db_session.commit()

    resp = client.post(
        f"/api/t/{tenant.slug}/helipagos/webhook", json={"id_sp": 26, "estado": "PROCESADA"}
    )
    assert resp.json()["status"] == "ignored"


def test_webhook_processes_payment(client, db_session, tenant, invoice):
    hp.save_credentials(db_session, tenant, "token-abc", "correct-apikey", "sandbox")
    invoice.helipagos_id_sp = "26"
    db_session.commit()

    resp = client.post(
        f"/api/t/{tenant.slug}/helipagos/webhook",
        json={"id_sp": 26, "estado": "PROCESADA", "referencia_externa": "inv-1"},
        headers={"apikey": "correct-apikey"},
    )
    assert resp.json()["status"] == "ok"

    db_session.refresh(invoice)
    assert invoice.pagado is True
