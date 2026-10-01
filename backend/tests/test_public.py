import datetime as dt

from app.models import Invoice


def test_get_tenant_info(client, tenant):
    resp = client.get(f"/api/t/{tenant.slug}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == tenant.slug
    assert body["name"] == tenant.name


def test_get_tenant_info_404_for_unknown_slug(client):
    resp = client.get("/api/t/does-not-exist")
    assert resp.status_code == 404


def test_lookup_member_success(client, tenant, member, invoice):
    resp = client.post(
        f"/api/t/{tenant.slug}/lookup",
        json={"numero_socio": member.numero_socio, "identificador": member.identificador},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["numero_socio"] == member.numero_socio
    assert body["saldo_total"] == float(invoice.monto)
    assert body["ultima_factura"]["id"] == invoice.id
    assert len(body["historial"]) == 1
    assert body["mp_connected"] is False


def test_lookup_member_strips_whitespace(client, tenant, member):
    resp = client.post(
        f"/api/t/{tenant.slug}/lookup",
        json={"numero_socio": f"  {member.numero_socio}  ", "identificador": f" {member.identificador} "},
    )
    assert resp.status_code == 200


def test_lookup_member_not_found(client, tenant, member):
    resp = client.post(
        f"/api/t/{tenant.slug}/lookup",
        json={"numero_socio": member.numero_socio, "identificador": "wrong-dni"},
    )
    assert resp.status_code == 404


def test_lookup_member_no_invoices_yields_empty_history(client, tenant, member):
    resp = client.post(
        f"/api/t/{tenant.slug}/lookup",
        json={"numero_socio": member.numero_socio, "identificador": member.identificador},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ultima_factura"] is None
    assert body["historial"] == []
    assert body["saldo_total"] == 0


def test_saldo_total_ignores_paid_invoices(client, db_session, tenant, member, import_batch):
    db_session.add_all(
        [
            Invoice(
                tenant_id=tenant.id,
                member_id=member.id,
                import_batch_id=import_batch.id,
                period_year=2026,
                period_month=1,
                monto=1000,
                pagado=True,
            ),
            Invoice(
                tenant_id=tenant.id,
                member_id=member.id,
                import_batch_id=import_batch.id,
                period_year=2026,
                period_month=2,
                monto=500,
                pagado=False,
            ),
        ]
    )
    db_session.commit()

    resp = client.post(
        f"/api/t/{tenant.slug}/lookup",
        json={"numero_socio": member.numero_socio, "identificador": member.identificador},
    )
    assert resp.status_code == 200
    assert resp.json()["saldo_total"] == 500.0


def test_pay_invoice_requires_mp_connected(client, tenant, member, invoice):
    resp = client.post(
        f"/api/t/{tenant.slug}/invoices/{invoice.id}/pay",
        json={"numero_socio": member.numero_socio, "identificador": member.identificador},
    )
    assert resp.status_code == 400
    assert "Mercado Pago" in resp.json()["detail"]


def test_pay_invoice_not_found(client, tenant, member):
    resp = client.post(
        f"/api/t/{tenant.slug}/invoices/99999/pay",
        json={"numero_socio": member.numero_socio, "identificador": member.identificador},
    )
    assert resp.status_code == 404


def test_pay_invoice_already_paid(client, db_session, tenant, member, invoice):
    invoice.pagado = True
    db_session.commit()

    resp = client.post(
        f"/api/t/{tenant.slug}/invoices/{invoice.id}/pay",
        json={"numero_socio": member.numero_socio, "identificador": member.identificador},
    )
    assert resp.status_code == 400
    assert "ya está pagada" in resp.json()["detail"]


def test_pay_invoice_wrong_member_credentials(client, tenant, member, invoice):
    resp = client.post(
        f"/api/t/{tenant.slug}/invoices/{invoice.id}/pay",
        json={"numero_socio": member.numero_socio, "identificador": "wrong"},
    )
    assert resp.status_code == 404


def test_download_boleta_pdf(client, tenant, member, invoice):
    resp = client.get(
        f"/api/t/{tenant.slug}/boleta.pdf",
        params={"numero_socio": member.numero_socio, "identificador": member.identificador},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


def test_download_boleta_pdf_no_invoices(client, tenant, member):
    resp = client.get(
        f"/api/t/{tenant.slug}/boleta.pdf",
        params={"numero_socio": member.numero_socio, "identificador": member.identificador},
    )
    assert resp.status_code == 404
