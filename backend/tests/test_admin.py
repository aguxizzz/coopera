import io

from sqlalchemy.orm import sessionmaker

from app.models import AdminUser, PdfImportProfile


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


def _sample_pdf_bytes():
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(50, 750, "N. Socio: 1001")
    c.drawString(50, 700, "Total $4,500.00")
    c.showPage()
    c.save()
    return buf.getvalue()


def test_import_members_pdf(client, db_session, tenant, admin_headers, monkeypatch):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_session.get_bind())
    monkeypatch.setattr("app.services.pdf_importer.SessionLocal", TestingSessionLocal)

    db_session.add(
        PdfImportProfile(
            tenant_id=tenant.id,
            field_patterns={
                "numero_socio": r"N\. Socio:\s*(\d+)",
                "monto": r"\$([0-9,]+\.[0-9]{2})",
            },
        )
    )
    db_session.commit()

    resp = client.post(
        f"/api/t/{tenant.slug}/admin/import-pdf",
        headers=admin_headers,
        data={"period_year": 2026, "period_month": 1},
        files=[("files", ("sector1.pdf", _sample_pdf_bytes(), "application/pdf"))],
    )
    assert resp.status_code == 200
    job_id = resp.json()["id"]

    resp = client.get(f"/api/t/{tenant.slug}/admin/import-pdf/status/{job_id}", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done"
    assert body["total_pages"] == 1
    assert body["import_batch_id"] is not None


def test_import_members_pdf_without_profile(client, tenant, admin_headers, monkeypatch, db_session):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_session.get_bind())
    monkeypatch.setattr("app.services.pdf_importer.SessionLocal", TestingSessionLocal)

    resp = client.post(
        f"/api/t/{tenant.slug}/admin/import-pdf",
        headers=admin_headers,
        data={"period_year": 2026, "period_month": 1},
        files=[("files", ("sector1.pdf", _sample_pdf_bytes(), "application/pdf"))],
    )
    assert resp.status_code == 200
    job_id = resp.json()["id"]

    resp = client.get(f"/api/t/{tenant.slug}/admin/import-pdf/status/{job_id}", headers=admin_headers)
    assert resp.json()["status"] == "error"


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


def test_mark_oldest_invoice_paid_picks_oldest_unpaid(client, db_session, tenant, admin_headers, member, invoice, import_batch):
    from app.models import Invoice

    newer = Invoice(
        tenant_id=tenant.id,
        member_id=member.id,
        import_batch_id=import_batch.id,
        period_year=2026,
        period_month=2,
        consumo=90.0,
        monto=3800.0,
        pagado=False,
    )
    db_session.add(newer)
    db_session.commit()

    resp = client.post(
        f"/api/t/{tenant.slug}/admin/members/{member.id}/mark-oldest-invoice-paid",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == invoice.id
    assert body["pagado"] is True

    db_session.refresh(newer)
    assert newer.pagado is False


def test_mark_oldest_invoice_paid_no_debt(client, tenant, admin_headers, member):
    resp = client.post(
        f"/api/t/{tenant.slug}/admin/members/{member.id}/mark-oldest-invoice-paid",
        headers=admin_headers,
    )
    assert resp.status_code == 404


def test_mark_oldest_invoice_paid_404_for_unknown_member(client, tenant, admin_headers):
    resp = client.post(
        f"/api/t/{tenant.slug}/admin/members/99999/mark-oldest-invoice-paid",
        headers=admin_headers,
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


def _create_staff(client, tenant, admin_headers, email="staff@coopera.test"):
    resp = client.post(
        f"/api/t/{tenant.slug}/admin/admins",
        headers=admin_headers,
        json={"email": email, "password": "staffpass1", "role": "staff"},
    )
    assert resp.status_code == 200
    return resp.json()


def _login(client, tenant, email, password):
    resp = client.post(
        f"/api/t/{tenant.slug}/admin/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_admin_create_defaults_to_staff_role(client, tenant, admin_headers):
    created = _create_staff(client, tenant, admin_headers)
    assert created["role"] == "staff"


def test_staff_cannot_connect_or_disconnect_mp(client, tenant, admin_headers):
    _create_staff(client, tenant, admin_headers)
    staff_headers = _login(client, tenant, "staff@coopera.test", "staffpass1")

    resp = client.get(f"/api/t/{tenant.slug}/admin/mp/connect-url", headers=staff_headers)
    assert resp.status_code == 403

    resp = client.delete(f"/api/t/{tenant.slug}/admin/mp", headers=staff_headers)
    assert resp.status_code == 403


def test_staff_cannot_manage_admins(client, tenant, admin_headers):
    _create_staff(client, tenant, admin_headers)
    staff_headers = _login(client, tenant, "staff@coopera.test", "staffpass1")

    resp = client.get(f"/api/t/{tenant.slug}/admin/admins", headers=staff_headers)
    assert resp.status_code == 403


def test_owner_can_list_and_manage_admins(client, tenant, admin, admin_headers):
    created = _create_staff(client, tenant, admin_headers)

    resp = client.get(f"/api/t/{tenant.slug}/admin/admins", headers=admin_headers)
    assert resp.status_code == 200
    emails = {row["email"] for row in resp.json()}
    assert {admin.email, "staff@coopera.test"} == emails

    resp = client.patch(
        f"/api/t/{tenant.slug}/admin/admins/{created['id']}/role",
        headers=admin_headers,
        json={"role": "owner"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "owner"

    resp = client.delete(f"/api/t/{tenant.slug}/admin/admins/{created['id']}", headers=admin_headers)
    assert resp.status_code == 200


def test_cannot_demote_or_delete_last_owner(client, tenant, admin, admin_headers):
    resp = client.patch(
        f"/api/t/{tenant.slug}/admin/admins/{admin.id}/role",
        headers=admin_headers,
        json={"role": "staff"},
    )
    assert resp.status_code == 400

    resp = client.delete(f"/api/t/{tenant.slug}/admin/admins/{admin.id}", headers=admin_headers)
    assert resp.status_code == 400


def test_owner_cannot_delete_self_via_admins_endpoint(client, tenant, admin, admin_headers, db_session):
    # add a second owner first so "last owner" isn't the blocker being tested
    from app.auth import hash_password
    from app.models import AdminUser

    other_owner = AdminUser(
        tenant_id=tenant.id,
        email="owner2@coopera.test",
        hashed_password=hash_password("ownerpass1"),
        role="owner",
    )
    db_session.add(other_owner)
    db_session.commit()

    resp = client.delete(f"/api/t/{tenant.slug}/admin/admins/{admin.id}", headers=admin_headers)
    assert resp.status_code == 400


def test_audit_log_records_sensitive_actions(client, tenant, admin, admin_headers, db_session):
    tenant.mp_access_token = "whatever-encrypted"
    db_session.commit()

    client.delete(f"/api/t/{tenant.slug}/admin/mp", headers=admin_headers)
    _create_staff(client, tenant, admin_headers)

    resp = client.get(f"/api/t/{tenant.slug}/admin/audit-log", headers=admin_headers)
    assert resp.status_code == 200
    actions = [row["action"] for row in resp.json()]
    assert "mp.disconnected" in actions
    assert "admin.created" in actions
    for row in resp.json():
        assert row["actor_email"] == admin.email
