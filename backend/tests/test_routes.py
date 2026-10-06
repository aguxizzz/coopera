import pytest

from app.auth import create_gestor_access_token
from app.models import Gestor, Meter, Reading


@pytest.fixture()
def meters(db_session, tenant, member):
    out = []
    for i, (cod, direc) in enumerate([("M-1", "Calle B 20"), ("M-2", "Calle A 10"), ("M-3", "Calle C 30")]):
        m = Meter(tenant_id=tenant.id, member_id=member.id, codigo=cod, tipo="luz", direccion=direc)
        db_session.add(m)
        out.append(m)
    db_session.commit()
    return out


def _base(tenant):
    return f"/api/t/{tenant.slug}"


def _make_route(client, tenant, headers, meters, who="admin", **extra):
    url = f"{_base(tenant)}/{'admin' if who == 'admin' else 'gestor'}/routes"
    body = {"nombre": "Ruta Norte", "meter_ids": [m.id for m in meters], **extra}
    return client.post(url, json=body, headers=headers)


def test_admin_creates_route_keeping_order(client, tenant, admin_headers, meters):
    order = [meters[2], meters[0], meters[1]]
    resp = _make_route(client, tenant, admin_headers, order)
    assert resp.status_code == 200
    body = resp.json()
    assert [p["codigo"] for p in body["paradas"]] == ["M-3", "M-1", "M-2"]
    assert body["cantidad_medidores"] == 3
    assert body["origen"] == "manual"


def test_route_rejects_duplicates_unknown_and_inactive_meters(client, tenant, admin_headers, meters, db_session):
    assert _make_route(client, tenant, admin_headers, [meters[0], meters[0]]).status_code == 400
    resp = client.post(
        f"{_base(tenant)}/admin/routes", json={"nombre": "x", "meter_ids": [9999]}, headers=admin_headers
    )
    assert resp.status_code == 404
    meters[0].activo = False
    db_session.commit()
    assert _make_route(client, tenant, admin_headers, [meters[0]]).status_code == 400


def test_admin_update_reorders_and_unassigns(client, tenant, admin_headers, gestor, meters):
    route = _make_route(client, tenant, admin_headers, meters, gestor_id=gestor.id).json()
    assert route["gestor_id"] == gestor.id
    resp = client.put(
        f"{_base(tenant)}/admin/routes/{route['id']}",
        json={"meter_ids": [meters[1].id, meters[0].id], "gestor_id": None},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [p["codigo"] for p in body["paradas"]] == ["M-2", "M-1"]
    assert body["gestor_id"] is None


def test_gestor_only_sees_own_or_unassigned_routes(client, tenant, admin_headers, gestor_headers, gestor, meters, db_session):
    other = Gestor(tenant_id=tenant.id, nombre="Otro", email="otro@coopera.test")
    db_session.add(other)
    db_session.commit()
    _make_route(client, tenant, admin_headers, meters[:1], gestor_id=gestor.id)
    _make_route(client, tenant, admin_headers, meters[1:2])
    _make_route(client, tenant, admin_headers, meters[2:], gestor_id=other.id)
    resp = client.get(f"{_base(tenant)}/gestor/routes", headers=gestor_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_gestor_cannot_start_route_assigned_to_other(client, tenant, admin_headers, gestor_headers, meters, db_session):
    other = Gestor(tenant_id=tenant.id, nombre="Otro", email="otro@coopera.test")
    db_session.add(other)
    db_session.commit()
    route = _make_route(client, tenant, admin_headers, meters, gestor_id=other.id).json()
    resp = client.post(f"{_base(tenant)}/gestor/routes/{route['id']}/start", headers=gestor_headers)
    assert resp.status_code == 403


def test_full_run_meter_by_meter(client, tenant, admin_headers, gestor_headers, meters):
    route = _make_route(client, tenant, admin_headers, meters).json()
    g = f"{_base(tenant)}/gestor"

    run = client.post(f"{g}/routes/{route['id']}/start", headers=gestor_headers).json()
    assert run["status"] == "en_curso"
    assert (run["total"], run["pendientes"]) == (3, 3)
    assert run["siguiente"]["codigo"] == "M-1"

    # Resuming returns the same run instead of creating another one.
    again = client.post(f"{g}/routes/{route['id']}/start", headers=gestor_headers).json()
    assert again["id"] == run["id"]
    current = client.get(f"{g}/runs/current", headers=gestor_headers).json()
    assert current["id"] == run["id"]

    stops = run["paradas"]
    r1 = client.post(f"{g}/runs/{run['id']}/stops/{stops[0]['id']}/reading", data={"valor": "100"}, headers=gestor_headers)
    assert r1.status_code == 200
    assert r1.json()["reading"]["valor"] == 100
    assert r1.json()["run"]["siguiente"]["codigo"] == "M-2"
    assert r1.json()["run"]["leidas"] == 1

    r2 = client.post(
        f"{g}/runs/{run['id']}/stops/{stops[1]['id']}/skip", json={"motivo": "nadie en casa"}, headers=gestor_headers
    )
    assert r2.json()["run"]["salteadas"] == 1
    assert r2.json()["run"]["siguiente"]["codigo"] == "M-3"

    r3 = client.post(f"{g}/runs/{run['id']}/stops/{stops[2]['id']}/reading", data={"valor": "50"}, headers=gestor_headers)
    final = r3.json()["run"]
    assert final["status"] == "completado"
    assert final["siguiente"] is None
    assert final["finished_at"] is not None

    assert client.get(f"{g}/runs/current", headers=gestor_headers).json() is None
    # Skipped meter has no reading; the others do.
    detail = client.get(f"{g}/runs/{run['id']}", headers=gestor_headers).json()
    assert [s["status"] for s in detail["paradas"]] == ["leido", "salteado", "leido"]

    admin_view = client.get(f"{_base(tenant)}/admin/route-runs/{run['id']}", headers=admin_headers)
    assert admin_view.status_code == 200
    assert admin_view.json()["leidas"] == 2


def test_resubmitting_a_stop_corrects_the_reading(client, tenant, admin_headers, gestor_headers, meters, db_session):
    route = _make_route(client, tenant, admin_headers, meters[:2]).json()
    g = f"{_base(tenant)}/gestor"
    run = client.post(f"{g}/routes/{route['id']}/start", headers=gestor_headers).json()
    stop = run["paradas"][0]
    url = f"{g}/runs/{run['id']}/stops/{stop['id']}/reading"
    client.post(url, data={"valor": "100"}, headers=gestor_headers)
    resp = client.post(url, data={"valor": "110"}, headers=gestor_headers)
    assert resp.status_code == 200
    assert resp.json()["reading"]["valor"] == 110
    assert db_session.query(Reading).filter(Reading.meter_id == stop["meter_id"]).count() == 1


def test_skipped_stop_can_be_read_later_and_read_stop_cannot_be_skipped(client, tenant, admin_headers, gestor_headers, meters):
    route = _make_route(client, tenant, admin_headers, meters[:2]).json()
    g = f"{_base(tenant)}/gestor"
    run = client.post(f"{g}/routes/{route['id']}/start", headers=gestor_headers).json()
    s0, s1 = run["paradas"]
    client.post(f"{g}/runs/{run['id']}/stops/{s0['id']}/skip", json={}, headers=gestor_headers)
    ok = client.post(f"{g}/runs/{run['id']}/stops/{s0['id']}/reading", data={"valor": "5"}, headers=gestor_headers)
    assert ok.status_code == 200
    assert ok.json()["run"]["salteadas"] == 0
    bad = client.post(f"{g}/runs/{run['id']}/stops/{s0['id']}/skip", json={}, headers=gestor_headers)
    assert bad.status_code == 409


def test_finish_and_cancel_close_run(client, tenant, admin_headers, gestor_headers, meters):
    route = _make_route(client, tenant, admin_headers, meters).json()
    g = f"{_base(tenant)}/gestor"
    run = client.post(f"{g}/routes/{route['id']}/start", headers=gestor_headers).json()
    done = client.post(f"{g}/runs/{run['id']}/cancel", headers=gestor_headers)
    assert done.json()["status"] == "cancelado"
    stop = run["paradas"][0]
    late = client.post(f"{g}/runs/{run['id']}/stops/{stop['id']}/skip", json={}, headers=gestor_headers)
    assert late.status_code == 409
    assert client.post(f"{g}/runs/{run['id']}/finish", headers=gestor_headers).status_code == 409


def test_run_belongs_to_its_gestor(client, tenant, admin_headers, gestor_headers, meters, db_session):
    route = _make_route(client, tenant, admin_headers, meters).json()
    g = f"{_base(tenant)}/gestor"
    run = client.post(f"{g}/routes/{route['id']}/start", headers=gestor_headers).json()
    other = Gestor(tenant_id=tenant.id, nombre="Otro", email="otro@coopera.test")
    db_session.add(other)
    db_session.commit()
    headers = {"Authorization": f"Bearer {create_gestor_access_token(other.id, tenant.id)}"}
    assert client.get(f"{g}/runs/{run['id']}", headers=headers).status_code == 403


def test_run_snapshot_unaffected_by_route_edits(client, tenant, admin_headers, gestor_headers, meters):
    route = _make_route(client, tenant, admin_headers, meters).json()
    g = f"{_base(tenant)}/gestor"
    run = client.post(f"{g}/routes/{route['id']}/start", headers=gestor_headers).json()
    client.put(f"{_base(tenant)}/admin/routes/{route['id']}", json={"meter_ids": [meters[0].id]}, headers=admin_headers)
    assert client.get(f"{g}/runs/{run['id']}", headers=gestor_headers).json()["total"] == 3


def test_delete_route_blocked_once_it_has_runs(client, tenant, admin_headers, gestor_headers, meters):
    route = _make_route(client, tenant, admin_headers, meters).json()
    unused = _make_route(client, tenant, admin_headers, meters[:1]).json()
    client.post(f"{_base(tenant)}/gestor/routes/{route['id']}/start", headers=gestor_headers)
    assert client.delete(f"{_base(tenant)}/admin/routes/{route['id']}", headers=admin_headers).status_code == 409
    assert client.delete(f"{_base(tenant)}/admin/routes/{unused['id']}", headers=admin_headers).status_code == 204


def test_auto_generate_preview_does_not_save(client, tenant, admin_headers, meters):
    resp = client.post(
        f"{_base(tenant)}/admin/routes/auto-generate",
        json={"meters_por_ruta": 2, "preview": True},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [r["cantidad_medidores"] for r in body] == [2, 1]
    assert all(r["id"] is None for r in body)
    assert client.get(f"{_base(tenant)}/admin/routes", headers=admin_headers).json() == []


def test_auto_generate_without_geo_orders_by_address(client, tenant, admin_headers, meters):
    resp = client.post(
        f"{_base(tenant)}/admin/routes/auto-generate", json={"meters_por_ruta": 10}, headers=admin_headers
    )
    assert resp.status_code == 200
    (route,) = resp.json()
    assert route["origen"] == "auto"
    assert [p["direccion"] for p in route["paradas"]] == ["Calle A 10", "Calle B 20", "Calle C 30"]


def test_auto_generate_groups_nearby_meters_using_last_location(client, tenant, admin_headers, meters, db_session):
    # M-1 and M-3 are neighbours; M-2 is far away.
    coords = {meters[0].id: (-34.6000, -58.4000), meters[1].id: (-34.9000, -58.9000), meters[2].id: (-34.6005, -58.4005)}
    for mid, (lat, lon) in coords.items():
        db_session.add(Reading(tenant_id=tenant.id, meter_id=mid, valor=1, lat=lat, lon=lon, created_at=__import__("datetime").datetime(2020, 1, 1)))
    db_session.commit()
    resp = client.post(
        f"{_base(tenant)}/admin/routes/auto-generate", json={"meters_por_ruta": 10}, headers=admin_headers
    )
    (route,) = resp.json()
    codes = [p["codigo"] for p in route["paradas"]]
    # The two neighbours must be consecutive stops, not split by the far one.
    assert abs(codes.index("M-1") - codes.index("M-3")) == 1


def test_auto_generate_solo_pendientes_skips_meters_read_this_month(client, tenant, admin_headers, gestor_headers, meters, db_session):
    client.post(f"{_base(tenant)}/gestor/meters/{meters[0].id}/readings", data={"valor": "10"}, headers=gestor_headers)
    resp = client.post(
        f"{_base(tenant)}/admin/routes/auto-generate", json={"preview": True}, headers=admin_headers
    )
    assert {p["codigo"] for p in resp.json()[0]["paradas"]} == {"M-2", "M-3"}


def test_auto_generate_with_nothing_to_do_is_400(client, tenant, admin_headers):
    resp = client.post(f"{_base(tenant)}/admin/routes/auto-generate", json={}, headers=admin_headers)
    assert resp.status_code == 400


def test_gestor_can_auto_generate_for_self(client, tenant, gestor_headers, gestor, meters):
    resp = client.post(f"{_base(tenant)}/gestor/routes/auto-generate", json={}, headers=gestor_headers)
    assert resp.status_code == 200
    assert resp.json()[0]["gestor_id"] == gestor.id


def test_routes_are_tenant_scoped(client, tenant, admin_headers, meters, db_session):
    from app.models import Tenant

    route = _make_route(client, tenant, admin_headers, meters).json()
    other = Tenant(slug="otra-coop-routes", name="Otra")
    db_session.add(other)
    db_session.commit()
    from app.auth import create_access_token
    from app.models import AdminUser

    a = AdminUser(tenant_id=other.id, email="a@otra.test", hashed_password="x")
    db_session.add(a)
    db_session.commit()
    h = {"Authorization": f"Bearer {create_access_token(a.id, other.id)}"}
    assert client.get(f"/api/t/{other.slug}/admin/routes/{route['id']}", headers=h).status_code == 404
