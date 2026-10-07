import datetime as dt

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


def _jornada(db_session, tenant, gestor, meters_in_order, start, minutes=10):
    """Readings by `gestor`, one every `minutes`, starting at `start`."""
    for i, m in enumerate(meters_in_order):
        db_session.add(
            Reading(
                tenant_id=tenant.id,
                meter_id=m.id,
                gestor_id=gestor.id,
                valor=i,
                created_at=start + dt.timedelta(minutes=minutes * i),
            )
        )
    db_session.commit()


@pytest.fixture()
def many_meters(db_session, tenant, member):
    out = []
    for i in range(12):
        m = Meter(tenant_id=tenant.id, member_id=member.id, codigo=f"N-{i:02d}", tipo="luz", direccion=f"Calle {i:02d}")
        db_session.add(m)
        out.append(m)
    db_session.commit()
    return out


def _auto(client, tenant, headers, **body):
    return client.post(f"{_base(tenant)}/admin/routes/auto-generate", json=body, headers=headers)


NOW = dt.datetime.utcnow()


def test_auto_generate_preview_does_not_save(client, tenant, admin_headers, meters):
    resp = _auto(client, tenant, admin_headers, meters_por_ruta=2, preview=True)
    assert resp.status_code == 200
    body = resp.json()
    assert [r["cantidad_medidores"] for r in body] == [2, 1]
    assert all(r["id"] is None for r in body)
    assert client.get(f"{_base(tenant)}/admin/routes", headers=admin_headers).json() == []


def test_auto_generate_without_history_orders_by_address(client, tenant, admin_headers, meters):
    (route,) = _auto(client, tenant, admin_headers, meters_por_ruta=10).json()
    assert route["origen"] == "auto"
    assert route["recorridos_base"] is None
    assert [p["direccion"] for p in route["paradas"]] == ["Calle A 10", "Calle B 20", "Calle C 30"]


def test_auto_generate_infers_route_from_a_jornada(client, tenant, admin_headers, gestor, many_meters, db_session):
    order = [many_meters[i] for i in (5, 2, 9, 0, 7, 3)]
    _jornada(db_session, tenant, gestor, order, NOW - dt.timedelta(days=10))
    routes = _auto(client, tenant, admin_headers, incluir_sin_historial=False).json()
    assert len(routes) == 1
    assert [p["codigo"] for p in routes[0]["paradas"]] == [m.codigo for m in order]
    assert routes[0]["recorridos_base"] == 1


def test_gap_splits_jornadas_and_short_ones_are_ignored(client, tenant, admin_headers, gestor, many_meters, db_session):
    start = NOW - dt.timedelta(days=10)
    morning = many_meters[:5]
    # 6h later (> default 4h gap): a different jornada, too short to count.
    afternoon = many_meters[5:7]
    _jornada(db_session, tenant, gestor, morning, start)
    _jornada(db_session, tenant, gestor, afternoon, start + dt.timedelta(hours=6))
    routes = _auto(client, tenant, admin_headers, incluir_sin_historial=False).json()
    assert len(routes) == 1
    assert {p["codigo"] for p in routes[0]["paradas"]} == {m.codigo for m in morning}


def test_small_pause_does_not_split_a_jornada(client, tenant, admin_headers, gestor, many_meters, db_session):
    start = NOW - dt.timedelta(days=10)
    # 3 + 3 meters with a 2h lunch in between: one jornada of 6.
    _jornada(db_session, tenant, gestor, many_meters[:3], start)
    _jornada(db_session, tenant, gestor, many_meters[3:6], start + dt.timedelta(hours=2, minutes=30))
    routes = _auto(client, tenant, admin_headers, incluir_sin_historial=False).json()
    assert len(routes) == 1 and routes[0]["cantidad_medidores"] == 6


def test_gap_horas_is_configurable(client, tenant, admin_headers, gestor, many_meters, db_session):
    start = NOW - dt.timedelta(days=10)
    _jornada(db_session, tenant, gestor, many_meters[:5], start)
    _jornada(db_session, tenant, gestor, many_meters[5:10], start + dt.timedelta(hours=6))
    two = _auto(client, tenant, admin_headers, incluir_sin_historial=False).json()
    assert len(two) == 2
    one = _auto(client, tenant, admin_headers, incluir_sin_historial=False, gap_horas=12, preview=True).json()
    assert len(one) == 1 and one[0]["cantidad_medidores"] == 10


def test_repeated_jornadas_merge_into_one_consensus_route(client, tenant, admin_headers, gestor, many_meters, db_session):
    m = many_meters
    # Same route three months in a row; the last one skips m[2] and swaps two stops.
    _jornada(db_session, tenant, gestor, [m[0], m[1], m[2], m[3], m[4], m[5]], NOW - dt.timedelta(days=65))
    _jornada(db_session, tenant, gestor, [m[0], m[1], m[2], m[3], m[4], m[5]], NOW - dt.timedelta(days=35))
    _jornada(db_session, tenant, gestor, [m[0], m[1], m[3], m[5], m[4], m[6]], NOW - dt.timedelta(days=5))
    routes = _auto(client, tenant, admin_headers, incluir_sin_historial=False).json()
    assert len(routes) == 1
    route = routes[0]
    assert route["recorridos_base"] == 3
    codes = [p["codigo"] for p in route["paradas"]]
    assert codes[:2] == ["N-00", "N-01"]
    assert set(codes) == {f"N-0{i}" for i in range(7)}  # m[2] kept (2 of 3), m[6] kept (latest)
    assert codes.index("N-03") < codes.index("N-05")


def test_different_routes_stay_separate_and_leftovers_get_their_own(client, tenant, admin_headers, gestor, many_meters, db_session):
    start = NOW - dt.timedelta(days=10)
    _jornada(db_session, tenant, gestor, many_meters[:5], start)
    _jornada(db_session, tenant, gestor, many_meters[5:10], start + dt.timedelta(days=1))
    routes = _auto(client, tenant, admin_headers).json()
    assert len(routes) == 3
    assert [r["recorridos_base"] for r in routes] == [1, 1, None]
    assert {p["codigo"] for p in routes[2]["paradas"]} == {"N-10", "N-11"}


def test_old_history_and_admin_readings_are_ignored(client, tenant, admin_headers, gestor, many_meters, db_session):
    _jornada(db_session, tenant, gestor, many_meters[:5], NOW - dt.timedelta(days=400))
    resp = _auto(client, tenant, admin_headers, incluir_sin_historial=False)
    assert resp.status_code == 400
    # Manual admin readings (no gestor) say nothing about a walking order.
    for i, m in enumerate(many_meters[:5]):
        db_session.add(Reading(tenant_id=tenant.id, meter_id=m.id, valor=1, created_at=NOW - dt.timedelta(days=3, minutes=-i)))
    db_session.commit()
    assert _auto(client, tenant, admin_headers, incluir_sin_historial=False).status_code == 400


def test_auto_generate_solo_pendientes_skips_meters_read_this_month(client, tenant, admin_headers, gestor_headers, meters):
    client.post(f"{_base(tenant)}/gestor/meters/{meters[0].id}/readings", data={"valor": "10"}, headers=gestor_headers)
    resp = _auto(client, tenant, admin_headers, preview=True, solo_pendientes=True)
    assert {p["codigo"] for p in resp.json()[0]["paradas"]} == {"M-2", "M-3"}


def test_auto_generate_with_nothing_to_do_is_400(client, tenant, admin_headers):
    assert _auto(client, tenant, admin_headers).status_code == 400


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


# --- Query counts: no per-meter / per-stop queries ----------------------------


def _count_queries(db_session, fn):
    from sqlalchemy import event

    statements = []

    def on_execute(conn, cursor, statement, *args):
        statements.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", on_execute)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", on_execute)
    return result, len(statements)


def _add_meters(db_session, tenant, member, count, start=0):
    out = []
    for i in range(start, start + count):
        m = Meter(tenant_id=tenant.id, member_id=member.id, codigo=f"Q-{i:03d}", tipo="luz", direccion=f"Calle {i}")
        db_session.add(m)
        out.append(m)
    db_session.commit()
    return out


def test_gestor_meters_query_count_does_not_grow_with_meters(client, tenant, member, gestor_headers, db_session):
    url = f"{_base(tenant)}/gestor/meters"
    small = _add_meters(db_session, tenant, member, 3)
    for i, m in enumerate(small):
        db_session.add(Reading(tenant_id=tenant.id, meter_id=m.id, valor=100 + i))
    db_session.commit()
    _, few = _count_queries(db_session, lambda: client.get(url, headers=gestor_headers))

    _add_meters(db_session, tenant, member, 40, start=100)
    res, many = _count_queries(db_session, lambda: client.get(url, headers=gestor_headers))

    assert res.status_code == 200 and len(res.json()) == 43
    assert many == few


def test_gestor_meters_reports_each_meters_latest_reading(client, tenant, member, gestor_headers, db_session):
    a, b = _add_meters(db_session, tenant, member, 2)
    now = dt.datetime.utcnow()
    db_session.add_all(
        [
            Reading(tenant_id=tenant.id, meter_id=a.id, valor=10, created_at=now - dt.timedelta(days=40)),
            Reading(tenant_id=tenant.id, meter_id=a.id, valor=25, created_at=now - dt.timedelta(days=2), anomala=True),
            Reading(tenant_id=tenant.id, meter_id=b.id, valor=7, created_at=now - dt.timedelta(days=5)),
        ]
    )
    db_session.commit()

    rows = {r["codigo"]: r for r in client.get(f"{_base(tenant)}/gestor/meters", headers=gestor_headers).json()}
    assert rows[a.codigo]["ultima_lectura"] == 25
    assert rows[a.codigo]["ultima_lectura_anomala"] is True
    assert rows[b.codigo]["ultima_lectura"] == 7


def test_run_query_count_does_not_grow_with_stops(client, tenant, member, gestor_headers, db_session):
    def start_run(meters):
        route = client.post(
            f"{_base(tenant)}/gestor/routes",
            json={"nombre": f"R{len(meters)}", "meter_ids": [m.id for m in meters]},
            headers=gestor_headers,
        ).json()
        return client.post(f"{_base(tenant)}/gestor/routes/{route['id']}/start", headers=gestor_headers).json()

    small = start_run(_add_meters(db_session, tenant, member, 3))
    _, few = _count_queries(
        db_session, lambda: client.get(f"{_base(tenant)}/gestor/runs/{small['id']}", headers=gestor_headers)
    )
    client.post(f"{_base(tenant)}/gestor/runs/{small['id']}/cancel", headers=gestor_headers)

    big = start_run(_add_meters(db_session, tenant, member, 30, start=100))
    res, many = _count_queries(
        db_session, lambda: client.get(f"{_base(tenant)}/gestor/runs/{big['id']}", headers=gestor_headers)
    )

    assert res.status_code == 200 and len(res.json()["paradas"]) == 30
    assert many == few


def test_run_stop_shows_value_before_its_own_reading(client, tenant, member, gestor_headers, db_session):
    meter = _add_meters(db_session, tenant, member, 1)[0]
    db_session.add(
        Reading(tenant_id=tenant.id, meter_id=meter.id, valor=100, created_at=dt.datetime.utcnow() - dt.timedelta(days=45))
    )
    db_session.commit()
    route = client.post(
        f"{_base(tenant)}/gestor/routes", json={"nombre": "R", "meter_ids": [meter.id]}, headers=gestor_headers
    ).json()
    run = client.post(f"{_base(tenant)}/gestor/routes/{route['id']}/start", headers=gestor_headers).json()
    stop = run["siguiente"]
    assert stop["ultima_lectura"] == 100

    client.post(
        f"{_base(tenant)}/gestor/runs/{run['id']}/stops/{stop['id']}/reading",
        data={"valor": "150"},
        headers=gestor_headers,
    )
    after = client.get(f"{_base(tenant)}/gestor/runs/{run['id']}", headers=gestor_headers).json()
    assert after["paradas"][0]["ultima_lectura"] == 100  # not the 150 it just produced
    assert after["paradas"][0]["reading_id"] is not None


# --- Recorrido and the monthly reading ---------------------------------------


def test_run_stop_exposes_last_reading_date_and_own_value(client, tenant, member, gestor_headers, db_session):
    meter = _add_meters(db_session, tenant, member, 1)[0]
    prev = Reading(tenant_id=tenant.id, meter_id=meter.id, valor=100, created_at=dt.datetime.utcnow() - dt.timedelta(days=40))
    db_session.add(prev)
    db_session.commit()
    g = f"{_base(tenant)}/gestor"
    route = client.post(f"{g}/routes", json={"nombre": "R", "meter_ids": [meter.id]}, headers=gestor_headers).json()
    run = client.post(f"{g}/routes/{route['id']}/start", headers=gestor_headers).json()
    stop = run["siguiente"]
    assert stop["ultima_lectura"] == 100
    assert stop["ultima_lectura_id"] == prev.id
    assert stop["ultima_lectura_fecha"] is not None
    assert stop["valor_leido"] is None

    client.post(f"{g}/runs/{run['id']}/stops/{stop['id']}/reading", data={"valor": "130"}, headers=gestor_headers)
    after = client.get(f"{g}/runs/{run['id']}", headers=gestor_headers).json()["paradas"][0]
    assert after["valor_leido"] == 130
    assert after["ultima_lectura"] == 100


def test_run_stop_corrects_a_reading_already_loaded_this_month(client, tenant, member, gestor_headers, db_session):
    meter = _add_meters(db_session, tenant, member, 1)[0]
    g = f"{_base(tenant)}/gestor"
    first = client.post(f"{g}/meters/{meter.id}/readings", data={"valor": "100"}, headers=gestor_headers).json()
    route = client.post(f"{g}/routes", json={"nombre": "R", "meter_ids": [meter.id]}, headers=gestor_headers).json()
    run = client.post(f"{g}/routes/{route['id']}/start", headers=gestor_headers).json()
    stop = run["siguiente"]
    assert stop["ultima_lectura_id"] == first["id"]

    res = client.post(f"{g}/runs/{run['id']}/stops/{stop['id']}/reading", data={"valor": "110"}, headers=gestor_headers)
    assert res.status_code == 200
    assert res.json()["reading"]["id"] == first["id"]  # same reading, corrected
    readings = db_session.query(Reading).filter(Reading.meter_id == meter.id).all()
    assert len(readings) == 1 and readings[0].valor == 110
    assert res.json()["run"]["leidas"] == 1


def test_run_stop_adds_a_new_reading_when_last_one_is_from_a_past_month(client, tenant, member, gestor_headers, db_session):
    meter = _add_meters(db_session, tenant, member, 1)[0]
    db_session.add(Reading(tenant_id=tenant.id, meter_id=meter.id, valor=100, created_at=dt.datetime.utcnow() - dt.timedelta(days=45)))
    db_session.commit()
    g = f"{_base(tenant)}/gestor"
    route = client.post(f"{g}/routes", json={"nombre": "R", "meter_ids": [meter.id]}, headers=gestor_headers).json()
    run = client.post(f"{g}/routes/{route['id']}/start", headers=gestor_headers).json()
    stop = run["siguiente"]
    res = client.post(f"{g}/runs/{run['id']}/stops/{stop['id']}/reading", data={"valor": "140"}, headers=gestor_headers)
    assert res.status_code == 200
    assert db_session.query(Reading).filter(Reading.meter_id == meter.id).count() == 2
