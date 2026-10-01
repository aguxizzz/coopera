import io

from app.models import AdminUser


def test_login_success(client, tenant, admin):
    resp = client.post(
        f"/api/t/{tenant.slug}/admin/login",
        json={"email": admin.email, "password": "secret123"},
    )
    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer"
    assert resp.json()["access_token"]


def test_login_wrong_password(client, tenant, admin):
    resp = client.post(
        f"/api/t/{tenant.slug}/admin/login",
        json={"email": admin.email, "password": "wrong"},
    )
    assert resp.status_code == 401


def test_login_unknown_email(client, tenant):
    resp = client.post(
        f"/api/t/{tenant.slug}/admin/login",
        json={"email": "nobody@coopera.test", "password": "secret123"},
    )
    assert resp.status_code == 401


def test_admin_routes_require_auth(client, tenant):
    resp = client.get(f"/api/t/{tenant.slug}/admin/members")
    assert resp.status_code == 401


def test_import_members_csv(client, tenant, admin_headers):
    csv_content = (
        "numero_socio,nombre,identificador,consumo,monto,vencimiento\n"
        "1001,Juana Perez,30111222,120.5,4500,2026-02-10\n"
        "1002,Pedro Gomez,30333444,80,3000,2026-02-10\n"
    ).encode("utf-8")

    resp = client.post(
        f"/api/t/{tenant.slug}/admin/import",
        headers=admin_headers,
        data={"period_year": 2026, "period_month": 1},
        files={"file": ("socios.csv", io.BytesIO(csv_content), "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows_processed"] == 2
    assert body["members_created"] == 2
    assert body["members_updated"] == 0


def test_import_members_rejects_bad_extension(client, tenant, admin_headers):
    resp = client.post(
        f"/api/t/{tenant.slug}/admin/import",
        headers=admin_headers,
        data={"period_year": 2026, "period_month": 1},
        files={"file": ("socios.txt", io.BytesIO(b"junk"), "text/plain")},
    )
    assert resp.status_code == 400


def test_list_members_includes_saldo(client, tenant, admin_headers, member, invoice):
    resp = client.get(f"/api/t/{tenant.slug}/admin/members", headers=admin_headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["numero_socio"] == member.numero_socio
    assert rows[0]["saldo_total"] == float(invoice.monto)


def test_list_member_invoices(client, tenant, admin_headers, member, invoice):
    resp = client.get(f"/api/t/{tenant.slug}/admin/members/{member.id}/invoices", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == invoice.id


def test_list_member_invoices_404_for_unknown_member(client, tenant, admin_headers):
    resp = client.get(f"/api/t/{tenant.slug}/admin/members/99999/invoices", headers=admin_headers)
    assert resp.status_code == 404


def test_update_invoice_pagado(client, tenant, admin_headers, invoice):
    resp = client.patch(
        f"/api/t/{tenant.slug}/admin/invoices/{invoice.id}",
        headers=admin_headers,
        json={"pagado": True},
    )
    assert resp.status_code == 200
    assert resp.json()["pagado"] is True


def test_update_invoice_pagado_404(client, tenant, admin_headers):
    resp = client.patch(
        f"/api/t/{tenant.slug}/admin/invoices/99999",
        headers=admin_headers,
        json={"pagado": True},
    )
    assert resp.status_code == 404


def test_delete_member(client, tenant, admin_headers, member):
    resp = client.delete(f"/api/t/{tenant.slug}/admin/members/{member.id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1

    resp = client.get(f"/api/t/{tenant.slug}/admin/members", headers=admin_headers)
    assert resp.json() == []


def test_delete_member_404(client, tenant, admin_headers):
    resp = client.delete(f"/api/t/{tenant.slug}/admin/members/99999", headers=admin_headers)
    assert resp.status_code == 404


def test_delete_members_bulk(client, tenant, admin_headers, member):
    resp = client.post(
        f"/api/t/{tenant.slug}/admin/members/delete",
        headers=admin_headers,
        json={"member_ids": [member.id, 99999]},
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1


def test_delete_members_bulk_empty_list(client, tenant, admin_headers):
    resp = client.post(
        f"/api/t/{tenant.slug}/admin/members/delete",
        headers=admin_headers,
        json={"member_ids": []},
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 0


def test_get_and_update_settings(client, tenant, admin_headers):
    resp = client.get(f"/api/t/{tenant.slug}/admin/settings", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["contact_email"] is None

    resp = client.put(
        f"/api/t/{tenant.slug}/admin/settings",
        headers=admin_headers,
        json={"contact_email": "hola@coopera.test", "primary_color": "#ff0000"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["contact_email"] == "hola@coopera.test"
    assert body["primary_color"] == "#ff0000"


def test_mp_status_not_configured(client, tenant, admin_headers):
    resp = client.get(f"/api/t/{tenant.slug}/admin/mp/status", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is False
    assert body["connected"] is False


def test_mp_connect_url_requires_configuration(client, tenant, admin_headers):
    resp = client.get(f"/api/t/{tenant.slug}/admin/mp/connect-url", headers=admin_headers)
    assert resp.status_code == 400


def test_mp_disconnect(client, db_session, tenant, admin_headers):
    tenant.mp_access_token = "whatever-encrypted"
    tenant.mp_user_id = "mp-123"
    db_session.commit()

    resp = client.delete(f"/api/t/{tenant.slug}/admin/mp", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["connected"] is False

    db_session.refresh(tenant)
    assert tenant.mp_access_token is None
    assert tenant.mp_user_id is None


def test_logo_upload_and_delete(client, tenant, admin_headers, tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    resp = client.post(
        f"/api/t/{tenant.slug}/admin/logo",
        headers=admin_headers,
        data={"kind": "primary"},
        files={"file": ("logo.png", io.BytesIO(png_bytes), "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["logo_primary_url"]

    resp = client.delete(
        f"/api/t/{tenant.slug}/admin/logo",
        headers=admin_headers,
        params={"kind": "primary"},
    )
    assert resp.status_code == 200
    assert resp.json()["logo_primary_url"] is None


def test_logo_upload_rejects_bad_kind(client, tenant, admin_headers):
    resp = client.post(
        f"/api/t/{tenant.slug}/admin/logo",
        headers=admin_headers,
        data={"kind": "tertiary"},
        files={"file": ("logo.png", io.BytesIO(b"abc"), "image/png")},
    )
    assert resp.status_code == 400


def test_logo_upload_rejects_unsupported_content_type(client, tenant, admin_headers, tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    resp = client.post(
        f"/api/t/{tenant.slug}/admin/logo",
        headers=admin_headers,
        data={"kind": "primary"},
        files={"file": ("logo.gif", io.BytesIO(b"abc"), "image/gif")},
    )
    assert resp.status_code == 400


def test_platform_token_can_access_tenant_admin_routes(client, tenant, platform_headers, member, invoice):
    resp = client.get(f"/api/t/{tenant.slug}/admin/members", headers=platform_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
