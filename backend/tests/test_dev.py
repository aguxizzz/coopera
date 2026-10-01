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
