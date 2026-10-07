from app.config import settings
from app.models import Tenant


def _device_login(client, tenant_slug, password="gestorsecret"):
    return client.post(
        f"/api/t/{tenant_slug}/gestor/device-login",
        json={"password": password},
    )


def _select_profile(client, tenant_slug, device_token, gestor_id):
    return client.post(
        f"/api/t/{tenant_slug}/gestor/select-profile",
        json={"device_token": device_token, "gestor_id": gestor_id},
    )


def _login(client, tenant_slug, gestor_id, password="gestorsecret"):
    device_token = _device_login(client, tenant_slug, password).json()["device_token"]
    return _select_profile(client, tenant_slug, device_token, gestor_id)


def test_gestor_device_login_lists_active_profiles(client, tenant, gestor):
    resp = _device_login(client, tenant.slug)
    assert resp.status_code == 200
    body = resp.json()
    assert body["device_token"]
    assert body["profiles"] == [{"id": gestor.id, "nombre": gestor.nombre}]


def test_gestor_device_login_wrong_password(client, tenant, gestor):
    resp = _device_login(client, tenant.slug, password="wrong")
    assert resp.status_code == 401


def test_gestor_device_login_without_shared_password_configured(client, tenant, db_session):
    tenant.gestor_shared_password_hash = None
    db_session.commit()
    resp = _device_login(client, tenant.slug)
    assert resp.status_code == 401


def test_gestor_select_profile_success(client, tenant, gestor):
    resp = _login(client, tenant.slug, gestor.id)
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]


def test_gestor_select_profile_rejects_invalid_device_token(client, tenant, gestor):
    resp = _select_profile(client, tenant.slug, "not-a-real-token", gestor.id)
    assert resp.status_code == 401


def test_gestor_select_profile_rejects_unknown_gestor(client, tenant, gestor):
    device_token = _device_login(client, tenant.slug).json()["device_token"]
    resp = _select_profile(client, tenant.slug, device_token, 999)
    assert resp.status_code == 404


def test_gestor_select_profile_rejects_inactive_gestor(client, tenant, gestor, db_session):
    device_token = _device_login(client, tenant.slug).json()["device_token"]
    gestor.activo = False
    db_session.commit()
    resp = _select_profile(client, tenant.slug, device_token, gestor.id)
    assert resp.status_code == 403


def test_gestor_select_profile_rejects_device_token_from_other_tenant(client, tenant, gestor, db_session):
    other_tenant = Tenant(slug="otra-coopera-device-test", name="Otra Cooperativa")
    db_session.add(other_tenant)
    db_session.commit()

    device_token = _device_login(client, tenant.slug).json()["device_token"]
    resp = _select_profile(client, other_tenant.slug, device_token, gestor.id)
    assert resp.status_code == 401


def test_gestor_refresh_issues_new_access_token(client, tenant, gestor):
    login_resp = _login(client, tenant.slug, gestor.id)
    refresh_token = login_resp.json()["refresh_token"]

    resp = client.post(
        f"/api/t/{tenant.slug}/gestor/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]

    # The new access token works against a protected route.
    resp = client.get(
        f"/api/t/{tenant.slug}/gestor/meters",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert resp.status_code == 200


def test_gestor_refresh_rotates_token_invalidating_the_old_one(client, tenant, gestor):
    login_resp = _login(client, tenant.slug, gestor.id)
    old_refresh_token = login_resp.json()["refresh_token"]

    client.post(f"/api/t/{tenant.slug}/gestor/refresh", json={"refresh_token": old_refresh_token})

    resp = client.post(
        f"/api/t/{tenant.slug}/gestor/refresh", json={"refresh_token": old_refresh_token}
    )
    assert resp.status_code == 401


def test_gestor_refresh_rejects_unknown_token(client, tenant, gestor):
    resp = client.post(
        f"/api/t/{tenant.slug}/gestor/refresh", json={"refresh_token": "not-a-real-token"}
    )
    assert resp.status_code == 401


def test_gestor_refresh_rejects_deactivated_gestor(client, tenant, gestor, db_session):
    login_resp = _login(client, tenant.slug, gestor.id)
    refresh_token = login_resp.json()["refresh_token"]

    gestor.activo = False
    db_session.commit()

    resp = client.post(f"/api/t/{tenant.slug}/gestor/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 403


def test_gestor_refresh_rejects_other_tenants_token(client, tenant, gestor, db_session):
    login_resp = _login(client, tenant.slug, gestor.id)
    refresh_token = login_resp.json()["refresh_token"]

    other_tenant = Tenant(slug="otra-coopera-test", name="Otra Cooperativa")
    db_session.add(other_tenant)
    db_session.commit()

    resp = client.post(
        f"/api/t/{other_tenant.slug}/gestor/refresh", json={"refresh_token": refresh_token}
    )
    assert resp.status_code == 401


def test_gestor_device_login_is_rate_limited(client, tenant, gestor):
    for _ in range(5):
        resp = _device_login(client, tenant.slug, password="wrong")
        assert resp.status_code == 401

    resp = _device_login(client, tenant.slug, password="wrong")
    assert resp.status_code == 429


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


def test_update_reading_corrects_value_and_recomputes_consumo(client, tenant, gestor_headers, meter):
    client.post(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
        headers=gestor_headers, data={"valor": 100},
    )
    created = client.post(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
        headers=gestor_headers, data={"valor": 150},
    ).json()

    resp = client.patch(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings/{created['id']}",
        headers=gestor_headers, data={"valor": 130},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valor"] == 130.0
    assert body["valor_anterior"] == 100.0
    assert body["consumo"] == 30

    rows = client.get(f"/api/t/{tenant.slug}/gestor/meters", headers=gestor_headers).json()
    assert rows[0]["ultima_lectura"] == 130.0


def test_update_reading_unknown_reading_404(client, tenant, gestor_headers, meter):
    resp = client.patch(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings/999",
        headers=gestor_headers, data={"valor": 10},
    )
    assert resp.status_code == 404


def test_update_reading_outside_current_cycle_is_rejected(client, tenant, gestor_headers, meter, db_session):
    import datetime as dt

    from app.models import Reading

    created = client.post(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
        headers=gestor_headers, data={"valor": 100},
    ).json()

    reading = db_session.query(Reading).filter(Reading.id == created["id"]).first()
    reading.created_at = dt.datetime.utcnow() - dt.timedelta(days=45)
    db_session.commit()

    resp = client.patch(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings/{created['id']}",
        headers=gestor_headers, data={"valor": 130},
    )
    assert resp.status_code == 409


def test_inactive_gestor_excluded_from_device_login_profiles(client, tenant, gestor, db_session):
    gestor.activo = False
    db_session.commit()
    resp = _device_login(client, tenant.slug)
    assert resp.status_code == 200
    assert resp.json()["profiles"] == []


def test_admin_can_set_shared_password_and_create_gestor(client, tenant, admin_headers, member):
    resp = client.put(
        f"/api/t/{tenant.slug}/admin/gestores/shared-password",
        headers=admin_headers,
        json={"password": "nueva-clave-compartida"},
    )
    assert resp.status_code == 204

    resp = client.post(
        f"/api/t/{tenant.slug}/admin/gestores",
        headers=admin_headers,
        json={"nombre": "Nueva Gestora", "email": "nueva@coopera.test"},
    )
    assert resp.status_code == 200
    assert resp.json()["activo"] is True

    device_resp = _device_login(client, tenant.slug, password="nueva-clave-compartida")
    assert device_resp.status_code == 200

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


def test_create_reading_accepts_real_jpeg_photo(client, tenant, gestor_headers, meter):
    resp = client.post(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
        headers=gestor_headers,
        data={"valor": 100},
        files={"foto": ("lectura.jpg", b"\xff\xd8\xff" + b"0" * 50, "image/jpeg")},
    )
    assert resp.status_code == 200
    assert resp.json()["foto_urls"] == [resp.json()["foto_urls"][0]]


def test_create_reading_accepts_up_to_three_photos(client, tenant, gestor_headers, meter):
    resp = client.post(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
        headers=gestor_headers,
        data={"valor": 100},
        files=[
            ("foto", ("a.jpg", b"\xff\xd8\xff" + b"0" * 50, "image/jpeg")),
            ("foto", ("b.jpg", b"\xff\xd8\xff" + b"1" * 50, "image/jpeg")),
            ("foto", ("c.jpg", b"\xff\xd8\xff" + b"2" * 50, "image/jpeg")),
        ],
    )
    assert resp.status_code == 200
    assert len(resp.json()["foto_urls"]) == 3


def test_create_reading_rejects_more_than_three_photos(client, tenant, gestor_headers, meter):
    resp = client.post(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
        headers=gestor_headers,
        data={"valor": 100},
        files=[
            ("foto", ("a.jpg", b"\xff\xd8\xff" + b"0" * 50, "image/jpeg")),
            ("foto", ("b.jpg", b"\xff\xd8\xff" + b"1" * 50, "image/jpeg")),
            ("foto", ("c.jpg", b"\xff\xd8\xff" + b"2" * 50, "image/jpeg")),
            ("foto", ("d.jpg", b"\xff\xd8\xff" + b"3" * 50, "image/jpeg")),
        ],
    )
    assert resp.status_code == 400


def test_create_reading_rejects_spoofed_content_type(client, tenant, gestor_headers, meter):
    """The client claims image/jpeg but the bytes aren't actually a JPEG
    (or any supported format) — must be rejected based on real content,
    not the client-supplied header."""
    resp = client.post(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
        headers=gestor_headers,
        data={"valor": 100},
        files={"foto": ("lectura.jpg", b"not-actually-an-image", "image/jpeg")},
    )
    assert resp.status_code == 400


def test_create_reading_rejects_oversized_photo(client, tenant, gestor_headers, meter, monkeypatch):
    monkeypatch.setattr(settings, "max_reading_photo_bytes", 10)
    resp = client.post(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
        headers=gestor_headers,
        data={"valor": 100},
        files={"foto": ("lectura.jpg", b"\xff\xd8\xff" + b"0" * 100, "image/jpeg")},
    )
    assert resp.status_code == 413


# --- QR login ----------------------------------------------------------


def _start_qr(client, tenant_slug, admin_headers):
    return client.post(f"/api/t/{tenant_slug}/admin/gestor-qr/start", headers=admin_headers)


def test_qr_login_full_happy_path(client, tenant, admin_headers, gestor):
    code = _start_qr(client, tenant.slug, admin_headers).json()["code"]

    # Nobody has scanned it yet.
    status_resp = client.get(f"/api/t/{tenant.slug}/admin/gestor-qr/{code}/status", headers=admin_headers)
    assert status_resp.json()["status"] == "pending"

    # The gestor app scans and claims it.
    claim_resp = client.post(f"/api/t/{tenant.slug}/gestor/qr-session/{code}/claim")
    assert claim_resp.status_code == 200
    assert claim_resp.json()["status"] == "claimed"

    # The admin now sees it waiting for confirmation and approves.
    status_resp = client.get(f"/api/t/{tenant.slug}/admin/gestor-qr/{code}/status", headers=admin_headers)
    assert status_resp.json()["status"] == "claimed"
    approve_resp = client.post(f"/api/t/{tenant.slug}/admin/gestor-qr/{code}/approve", headers=admin_headers)
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    # The gestor app polls and gets the device_token + profiles exactly once.
    poll_resp = client.get(f"/api/t/{tenant.slug}/gestor/qr-session/{code}")
    body = poll_resp.json()
    assert body["status"] == "approved"
    assert body["device_token"]
    assert body["profiles"] == [{"id": gestor.id, "nombre": gestor.nombre}]

    # A second poll can't replay the token.
    poll_again = client.get(f"/api/t/{tenant.slug}/gestor/qr-session/{code}")
    assert poll_again.json()["status"] == "expired"

    # And the device_token works for select-profile, same as the password flow.
    select_resp = client.post(
        f"/api/t/{tenant.slug}/gestor/select-profile",
        json={"device_token": body["device_token"], "gestor_id": gestor.id},
    )
    assert select_resp.status_code == 200
    assert select_resp.json()["access_token"]


def test_qr_login_admin_can_deny(client, tenant, admin_headers):
    code = _start_qr(client, tenant.slug, admin_headers).json()["code"]
    client.post(f"/api/t/{tenant.slug}/gestor/qr-session/{code}/claim")

    deny_resp = client.post(f"/api/t/{tenant.slug}/admin/gestor-qr/{code}/deny", headers=admin_headers)
    assert deny_resp.json()["status"] == "denied"

    poll_resp = client.get(f"/api/t/{tenant.slug}/gestor/qr-session/{code}")
    assert poll_resp.json()["status"] == "denied"


def test_qr_login_cannot_approve_before_claim(client, tenant, admin_headers):
    code = _start_qr(client, tenant.slug, admin_headers).json()["code"]
    resp = client.post(f"/api/t/{tenant.slug}/admin/gestor-qr/{code}/approve", headers=admin_headers)
    assert resp.status_code == 409


def test_qr_login_expires(client, tenant, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "gestor_qr_expire_minutes", -1)
    code = _start_qr(client, tenant.slug, admin_headers).json()["code"]

    claim_resp = client.post(f"/api/t/{tenant.slug}/gestor/qr-session/{code}/claim")
    assert claim_resp.json()["status"] == "expired"

    status_resp = client.get(f"/api/t/{tenant.slug}/admin/gestor-qr/{code}/status", headers=admin_headers)
    assert status_resp.json()["status"] == "expired"


def test_qr_login_unknown_code_404(client, tenant, admin_headers):
    resp = client.get(f"/api/t/{tenant.slug}/admin/gestor-qr/not-a-real-code/status", headers=admin_headers)
    assert resp.status_code == 404

    resp = client.post(f"/api/t/{tenant.slug}/gestor/qr-session/not-a-real-code/claim")
    assert resp.status_code == 404


def test_qr_login_code_scoped_to_tenant(client, tenant, admin_headers, db_session):
    other_tenant = Tenant(slug="otra-coopera-qr-test", name="Otra Cooperativa")
    db_session.add(other_tenant)
    db_session.commit()

    code = _start_qr(client, tenant.slug, admin_headers).json()["code"]
    resp = client.post(f"/api/t/{other_tenant.slug}/gestor/qr-session/{code}/claim")
    assert resp.status_code == 404


def test_reading_saved_with_observacion_is_kept_and_flagged_for_review(client, tenant, gestor_headers, meter):
    # Within the server's normal range, but the gestor saw something worth
    # telling the admin (the app asks for a reason on its own warnings).
    for v in [100, 110, 120, 130]:
        client.post(
            f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
            headers=gestor_headers, data={"valor": v},
        )
    resp = client.post(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
        headers=gestor_headers,
        data={"valor": 160, "observacion": "  Pérdida visible "},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["observacion"] == "Pérdida visible"
    assert body["anomala"] is True

    resp = client.get(f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings", headers=gestor_headers)
    assert resp.json()[0]["observacion"] == "Pérdida visible"


def test_reading_without_observacion_has_none(client, tenant, gestor_headers, meter):
    resp = client.post(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
        headers=gestor_headers, data={"valor": 100, "observacion": "   "},
    )
    assert resp.status_code == 200
    assert resp.json()["observacion"] is None
    assert resp.json()["anomala"] is False


def test_correction_keeps_the_observacion_already_given(client, tenant, gestor_headers, meter):
    created = client.post(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings",
        headers=gestor_headers, data={"valor": 100, "observacion": "Medidor cambiado"},
    ).json()
    resp = client.patch(
        f"/api/t/{tenant.slug}/gestor/meters/{meter.id}/readings/{created['id']}",
        headers=gestor_headers, data={"valor": 105},
    )
    assert resp.status_code == 200
    assert resp.json()["observacion"] == "Medidor cambiado"
    assert resp.json()["anomala"] is True
