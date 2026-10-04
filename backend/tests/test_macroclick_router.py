from app.services import macroclick as mc


def test_webhook_ignores_unknown_tenant(client):
    resp = client.post(
        "/api/t/unknown-slug/macroclick/webhook",
        json={"TransaccionComercioId": "1-171234", "EstadoId": 3},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_webhook_ignores_tenant_without_macroclick(client, tenant):
    resp = client.post(
        f"/api/t/{tenant.slug}/macroclick/webhook",
        json={"TransaccionComercioId": "1-171234", "EstadoId": 3},
    )
    assert resp.json()["status"] == "ignored"


def test_webhook_processes_payment(client, db_session, tenant, invoice):
    mc.save_credentials(db_session, tenant, "comercio-1", "0000000000", "secret-xyz", "sandbox")

    resp = client.post(
        f"/api/t/{tenant.slug}/macroclick/webhook",
        json={"TransaccionComercioId": f"{invoice.id}-171234", "EstadoId": 3},
    )
    assert resp.json()["status"] == "ok"

    db_session.refresh(invoice)
    assert invoice.pagado is True


def test_pay_macroclick_requires_connection(client, tenant, member, invoice):
    resp = client.post(
        f"/api/t/{tenant.slug}/invoices/{invoice.id}/pay-macroclick",
        json={"numero_socio": member.numero_socio, "identificador": member.identificador},
    )
    assert resp.status_code == 400


def test_pay_macroclick_returns_checkout_form_url(client, db_session, tenant, member, invoice):
    mc.save_credentials(db_session, tenant, "comercio-1", "0000000000", "secret-xyz", "sandbox")

    resp = client.post(
        f"/api/t/{tenant.slug}/invoices/{invoice.id}/pay-macroclick",
        json={"numero_socio": member.numero_socio, "identificador": member.identificador},
    )
    assert resp.status_code == 200
    init_point = resp.json()["init_point"]
    assert f"/api/t/{tenant.slug}/macroclick/checkout-form/" in init_point

    token = init_point.rsplit("/", 1)[-1]
    form_resp = client.get(f"/api/t/{tenant.slug}/macroclick/checkout-form/{token}")
    assert form_resp.status_code == 200
    assert "<script>" in form_resp.text
    assert mc.MACROCLICK_SANDBOX_BASE in form_resp.text


def test_checkout_form_rejects_invalid_token(client, tenant):
    resp = client.get(f"/api/t/{tenant.slug}/macroclick/checkout-form/not-a-real-token")
    assert resp.status_code == 400


def test_checkout_form_rejects_already_paid_invoice(client, db_session, tenant, member, invoice):
    mc.save_credentials(db_session, tenant, "comercio-1", "0000000000", "secret-xyz", "sandbox")
    invoice.pagado = True
    db_session.commit()

    token = mc.build_checkout_token(tenant.slug, invoice.id)
    resp = client.get(f"/api/t/{tenant.slug}/macroclick/checkout-form/{token}")
    assert resp.status_code == 400
