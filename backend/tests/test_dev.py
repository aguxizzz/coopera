from app.models import Meter


def test_dev_login_success(client, platform_user):
    resp = client.post("/api/dev/login", json={"email": platform_user.email, "password": "devsecret"})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_dev_login_wrong_password(client, platform_user):
    resp = client.post("/api/dev/login", json={"email": platform_user.email, "password": "wrong"})
    assert resp.status_code == 401


def test_dev_routes_require_platform_token(client, admin_headers, tenant):
    resp = client.get("/api/dev/tenants", headers=admin_headers)
    assert resp.status_code == 403


def test_dev_routes_require_auth(client):
    resp = client.get("/api/dev/tenants")
    assert resp.status_code == 401


def test_create_tenant(client, platform_headers):
    resp = client.post(
        "/api/dev/tenants",
        headers=platform_headers,
        json={
            "slug": "nueva-coop",
            "name": "Nueva Cooperativa",
            "admin_email": "admin@nueva.test",
            "admin_password": "pass1234",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "nueva-coop"

    resp = client.post(
        f"/api/t/nueva-coop/admin/login",
        json={"email": "admin@nueva.test", "password": "pass1234"},
    )
    assert resp.status_code == 200


def test_create_tenant_duplicate_slug(client, platform_headers, tenant):
    resp = client.post(
        "/api/dev/tenants",
        headers=platform_headers,
        json={
            "slug": tenant.slug,
            "name": "Otra",
            "admin_email": "x@x.test",
            "admin_password": "pass1234",
        },
    )
    assert resp.status_code == 400


def test_list_tenants(client, platform_headers, tenant, admin, member):
    resp = client.get("/api/dev/tenants", headers=platform_headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["slug"] == tenant.slug
    assert rows[0]["admin_count"] == 1
    assert rows[0]["member_count"] == 1


def test_get_tenant_detail_404(client, platform_headers):
    resp = client.get("/api/dev/tenants/unknown-slug", headers=platform_headers)
    assert resp.status_code == 404


def test_list_tenant_admins(client, platform_headers, tenant, admin):
    resp = client.get(f"/api/dev/tenants/{tenant.slug}/admins", headers=platform_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["email"] == admin.email


def test_create_tenant_admin(client, platform_headers, tenant):
    resp = client.post(
        f"/api/dev/tenants/{tenant.slug}/admins",
        headers=platform_headers,
        json={"email": "second@coopera.test", "password": "pass1234"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "second@coopera.test"


def test_create_tenant_admin_duplicate_email(client, platform_headers, tenant, admin):
    resp = client.post(
        f"/api/dev/tenants/{tenant.slug}/admins",
        headers=platform_headers,
        json={"email": admin.email, "password": "pass1234"},
    )
    assert resp.status_code == 400


def test_reset_admin_password(client, platform_headers, tenant, admin):
    resp = client.post(
        f"/api/dev/tenants/{tenant.slug}/admins/{admin.id}/reset-password",
        headers=platform_headers,
        json={"password": "brand-new-pass"},
    )
    assert resp.status_code == 200

    resp = client.post(
        f"/api/t/{tenant.slug}/admin/login",
        json={"email": admin.email, "password": "brand-new-pass"},
    )
    assert resp.status_code == 200


def test_delete_tenant_admin(client, platform_headers, tenant, admin):
    resp = client.delete(f"/api/dev/tenants/{tenant.slug}/admins/{admin.id}", headers=platform_headers)
    assert resp.status_code == 200

    resp = client.get(f"/api/dev/tenants/{tenant.slug}/admins", headers=platform_headers)
    assert resp.json() == []


def test_delete_tenant_admin_404(client, platform_headers, tenant):
    resp = client.delete(f"/api/dev/tenants/{tenant.slug}/admins/99999", headers=platform_headers)
    assert resp.status_code == 404


def _sample_pdf_bytes():
    import io

    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(50, 750, "N. Socio: 42")
    c.drawString(50, 700, "Total $1,234.56")
    c.showPage()
    c.save()
    return buf.getvalue()


def test_test_pdf_profile_preview(client, platform_headers, tenant):
    resp = client.post(
        f"/api/dev/tenants/{tenant.slug}/pdf-profile/test",
        headers=platform_headers,
        data={"field_patterns": '{"numero_socio": "N\\\\. Socio:\\\\s*(\\\\d+)", "monto": "\\\\$([0-9,]+\\\\.[0-9]{2})"}'},
        files={"file": ("sample.pdf", _sample_pdf_bytes(), "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["fields"]["numero_socio"] == "42"
    assert body[0]["fields"]["monto"] == "1234.56"


def test_test_pdf_profile_invalid_json(client, platform_headers, tenant):
    resp = client.post(
        f"/api/dev/tenants/{tenant.slug}/pdf-profile/test",
        headers=platform_headers,
        data={"field_patterns": "not json"},
        files={"file": ("sample.pdf", _sample_pdf_bytes(), "application/pdf")},
    )
    assert resp.status_code == 400


def test_save_and_get_pdf_profile(client, platform_headers, tenant):
    resp = client.get(f"/api/dev/tenants/{tenant.slug}/pdf-profile", headers=platform_headers)
    assert resp.status_code == 200
    assert resp.json() is None

    resp = client.put(
        f"/api/dev/tenants/{tenant.slug}/pdf-profile",
        headers=platform_headers,
        json={"field_patterns": {"numero_socio": r"N\. Socio:\s*(\d+)"}},
    )
    assert resp.status_code == 200
    assert resp.json()["field_patterns"]["numero_socio"]

    resp = client.get(f"/api/dev/tenants/{tenant.slug}/pdf-profile", headers=platform_headers)
    assert resp.status_code == 200
    assert resp.json()["field_patterns"]["numero_socio"]


def test_save_pdf_profile_requires_numero_socio(client, platform_headers, tenant):
    resp = client.put(
        f"/api/dev/tenants/{tenant.slug}/pdf-profile",
        headers=platform_headers,
        json={"field_patterns": {"monto": r"\$([0-9,]+\.[0-9]{2})"}},
    )
    assert resp.status_code == 400


def test_update_tenant_modules_turns_portal_off_and_on(client, platform_headers, tenant):
    resp = client.patch(
        f"/api/dev/tenants/{tenant.slug}/modules",
        headers=platform_headers,
        json={"portal_socios_enabled": False},
    )
    assert resp.status_code == 200
    assert resp.json()["portal_socios_enabled"] is False

    listed = client.get("/api/dev/tenants", headers=platform_headers).json()
    assert listed[0]["portal_socios_enabled"] is False

    resp = client.patch(
        f"/api/dev/tenants/{tenant.slug}/modules",
        headers=platform_headers,
        json={"portal_socios_enabled": True},
    )
    assert resp.json()["portal_socios_enabled"] is True


def test_update_tenant_modules_requires_platform_token(client, admin_headers, tenant):
    resp = client.patch(
        f"/api/dev/tenants/{tenant.slug}/modules",
        headers=admin_headers,
        json={"portal_socios_enabled": False},
    )
    assert resp.status_code == 403


def test_update_tenant_services_gives_existing_members_their_meters(
    client, platform_headers, tenant, member, db_session
):
    resp = client.patch(
        f"/api/dev/tenants/{tenant.slug}/services",
        headers=platform_headers,
        json={"servicios_medidos": ["agua", "luz", "agua"]},
    )
    assert resp.status_code == 200
    assert resp.json()["servicios_medidos"] == ["agua", "luz"]

    listed = client.get("/api/dev/tenants", headers=platform_headers).json()
    assert listed[0]["servicios_medidos"] == ["agua", "luz"]

    # Sacar un servicio no borra medidores, y repetir no los duplica.
    resp = client.patch(
        f"/api/dev/tenants/{tenant.slug}/services",
        headers=platform_headers,
        json={"servicios_medidos": ["luz"]},
    )
    assert resp.json()["servicios_medidos"] == ["luz"]
    codigos = sorted(m.codigo for m in db_session.query(Meter).filter(Meter.member_id == member.id))
    assert codigos == ["1001-agua", "1001-luz"]


def test_update_tenant_services_rejects_unknown_service(client, platform_headers, tenant):
    resp = client.patch(
        f"/api/dev/tenants/{tenant.slug}/services",
        headers=platform_headers,
        json={"servicios_medidos": ["cable"]},
    )
    assert resp.status_code == 422


def test_update_tenant_services_requires_platform_token(client, admin_headers, tenant):
    resp = client.patch(
        f"/api/dev/tenants/{tenant.slug}/services",
        headers=admin_headers,
        json={"servicios_medidos": ["luz"]},
    )
    assert resp.status_code == 403
