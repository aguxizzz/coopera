def test_gestor_login_success(client, tenant, gestor):
    resp = client.post(
        f"/api/t/{tenant.slug}/gestor/login",
        json={"email": gestor.email, "password": "gestorsecret"},
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_gestor_login_wrong_password(client, tenant, gestor):
    resp = client.post(
        f"/api/t/{tenant.slug}/gestor/login",
        json={"email": gestor.email, "password": "wrong"},
    )
    assert resp.status_code == 401


def test_gestor_routes_require_auth(client, tenant):
    resp = client.get(f"/api/t/{tenant.slug}/gestor/meters")
    assert resp.status_code == 401


def test_admin_token_cannot_access_gestor_routes(client, tenant, admin_headers):
    resp = client.get(f"/api/t/{tenant.slug}/gestor/meters", headers=admin_headers)
    assert resp.status_code == 403


def test_gestor_token_cannot_access_admin_routes(client, tenant, gestor_headers):
    resp = client.get(f"/api/t/{tenant.slug}/admin/members", headers=gestor_headers)
    assert resp.status_code == 401


def test_list_meters_includes_last_reading(client, tenant, gestor_headers, meter):
    resp = client.post(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
        headers=gestor_headers,
        data={"valor": 100},
    )
    assert resp.status_code == 200

    resp = client.get(f"/api/t/{tenant.slug}/gestor/meters", headers=gestor_headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["ultima_lectura"] == 100.0
    assert rows[0]["numero_socio"] == "1001"


def test_first_reading_has_no_consumo_and_is_not_anomalous(client, tenant, gestor_headers, meter):
    resp = client.post(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
        headers=gestor_headers,
        data={"valor": 500},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valor_anterior"] is None
    assert body["consumo"] is None
    assert body["anomala"] is False


def test_reading_lower_than_previous_is_flagged_anomalous(client, tenant, gestor_headers, meter):
    client.post(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
        headers=gestor_headers, data={"valor": 500},
    )
    resp = client.post(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
        headers=gestor_headers, data={"valor": 480},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["consumo"] == -20
    assert body["anomala"] is True


def test_reading_far_above_historic_average_is_flagged_anomalous(client, tenant, gestor_headers, meter):
    # Build a steady history of ~10 units per reading.
    values = [100, 110, 120, 130]
    for v in values:
        client.post(
            f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
            headers=gestor_headers, data={"valor": v},
        )

    # A jump of +200 (vs. an average delta of ~10) should be flagged.
    resp = client.post(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
        headers=gestor_headers, data={"valor": 330},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["consumo"] == 200
    assert body["anomala"] is True


def test_reading_within_normal_range_is_not_flagged(client, tenant, gestor_headers, meter):
    values = [100, 110, 120, 130]
    for v in values:
        client.post(
            f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
            headers=gestor_headers, data={"valor": v},
        )

    resp = client.post(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
        headers=gestor_headers, data={"valor": 142},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["consumo"] == 12
    assert body["anomala"] is False


def test_create_reading_unknown_meter_404(client, tenant, gestor_headers):
    resp = client.post(
        f"/api/t/{tenant.slug}/gestor/meters/999/readings",
        headers=gestor_headers, data={"valor": 10},
    )
    assert resp.status_code == 404


def test_inactive_gestor_cannot_login(client, tenant, gestor, db_session):
    gestor.activo = False
    db_session.commit()
    resp = client.post(
        f"/api/t/{tenant.slug}/gestor/login",
        json={"email": gestor.email, "password": "gestorsecret"},
    )
    assert resp.status_code == 403


def test_admin_can_create_meter_and_gestor(client, tenant, admin_headers, member):
    resp = client.post(
        f"/api/t/{tenant.slug}/admin/gestores",
        headers=admin_headers,
        json={"nombre": "Nueva Gestora", "email": "nueva@coopera.test", "password": "secret123"},
    )
    assert resp.status_code == 200
    assert resp.json()["activo"] is True

    resp = client.post(
        f"/api/t/{tenant.slug}/admin/meters",
        headers=admin_headers,
        json={"member_id": member.id, "codigo": "MED-900", "tipo": "agua"},
    )
    assert resp.status_code == 200
    assert resp.json()["numero_socio"] == member.numero_socio


def test_admin_can_deactivate_gestor(client, tenant, admin_headers, gestor):
    resp = client.patch(
        f"/api/t/{tenant.slug}/admin/gestores/{gestor.id}/activo",
        headers=admin_headers,
        json={"activo": False},
    )
    assert resp.status_code == 200
    assert resp.json()["activo"] is False
