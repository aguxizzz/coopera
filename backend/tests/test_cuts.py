import pytest

from app.auth import create_access_token, hash_password
from app.models import AdminUser, Meter, ServiceCut

JPEG = b"\xff\xd8\xff" + b"0" * 50


@pytest.fixture()
def meters(db_session, tenant, member):
    out = [
        Meter(tenant_id=tenant.id, member_id=member.id, codigo="L-1", tipo="luz", direccion="Calle A 1"),
        Meter(tenant_id=tenant.id, member_id=member.id, codigo="G-1", tipo="gas", direccion="Calle A 1"),
    ]
    db_session.add_all(out)
    db_session.commit()
    return out


def _admin(tenant):
    return f"/api/t/{tenant.slug}/admin"


def _gestor(tenant):
    return f"/api/t/{tenant.slug}/gestor"


def _order(client, tenant, headers, member, **body):
    body = {"motivo": "impago", **body}
    return client.post(f"{_admin(tenant)}/members/{member.id}/cuts", json=body, headers=headers)


def test_order_cut_for_one_meter(client, tenant, admin_headers, member, meters):
    resp = _order(client, tenant, admin_headers, member, meter_ids=[meters[0].id], detalle="3 facturas")
    assert resp.status_code == 200
    [cut] = resp.json()
    assert cut["codigo"] == "L-1"
    assert cut["estado"] == "ordenado"
    assert cut["motivo"] == "impago"
    assert cut["ordenado_por_email"] == "admin@coopera.test"


def test_order_cut_for_all_meters_skips_those_already_cut(client, tenant, admin_headers, member, meters):
    _order(client, tenant, admin_headers, member, meter_ids=[meters[0].id])
    resp = _order(client, tenant, admin_headers, member, motivo="multa")
    assert [c["codigo"] for c in resp.json()] == ["G-1"]
    assert _order(client, tenant, admin_headers, member).status_code == 400


def test_order_cut_rejects_meter_already_cut_and_foreign_meter(client, tenant, admin_headers, member, meters):
    _order(client, tenant, admin_headers, member, meter_ids=[meters[0].id])
    assert _order(client, tenant, admin_headers, member, meter_ids=[meters[0].id]).status_code == 400
    assert _order(client, tenant, admin_headers, member, meter_ids=[99999]).status_code == 404


def test_staff_can_order_cut(client, tenant, db_session, member, meters):
    staff = AdminUser(
        tenant_id=tenant.id, email="staff@coopera.test", hashed_password=hash_password("x" * 8), role="staff"
    )
    db_session.add(staff)
    db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(staff.id, tenant.id)}"}
    assert _order(client, tenant, headers, member, meter_ids=[meters[0].id]).status_code == 200


def test_cut_requires_admin_auth(client, tenant, member, meters, gestor_headers):
    url = f"{_admin(tenant)}/members/{member.id}/cuts"
    assert client.post(url, json={"motivo": "otro"}).status_code in (401, 403)
    assert client.post(url, json={"motivo": "otro"}, headers=gestor_headers).status_code in (401, 403)


def test_full_lifecycle(client, tenant, admin_headers, gestor_headers, member, meters):
    [cut] = _order(client, tenant, admin_headers, member, meter_ids=[meters[0].id]).json()
    base = f"{_gestor(tenant)}/cuts"

    assert [c["id"] for c in client.get(base, headers=gestor_headers).json()] == [cut["id"]]

    # Restore can't be done before the cut itself.
    assert client.post(f"{base}/{cut['id']}/restore", headers=gestor_headers).status_code == 409

    done = client.post(
        f"{base}/{cut['id']}/execute",
        data={"nota": "Cortado en el pilar"},
        files={"foto": ("c.jpg", JPEG, "image/jpeg")},
        headers=gestor_headers,
    )
    assert done.status_code == 200
    body = done.json()
    assert body["estado"] == "ejecutado"
    assert body["ejecutado_por_nombre"] == "Carlos Gestor"
    assert body["ejecucion_nota"] == "Cortado en el pilar"
    assert len(body["ejecucion_foto_urls"]) == 1
    assert client.post(f"{base}/{cut['id']}/execute", headers=gestor_headers).status_code == 409

    order = client.post(f"{_admin(tenant)}/cuts/{cut['id']}/order-restore", headers=admin_headers)
    assert order.json()["estado"] == "reposicion_ordenada"

    back = client.post(f"{base}/{cut['id']}/restore", data={"nota": "Reconectado"}, headers=gestor_headers)
    assert back.json()["estado"] == "repuesto"
    assert back.json()["repuesto_por_nombre"] == "Carlos Gestor"

    # A closed cut is no longer in force, so the meter can be cut again.
    assert client.get(base, headers=gestor_headers).json() == []
    assert _order(client, tenant, admin_headers, member, meter_ids=[meters[0].id]).status_code == 200


def test_cancel_before_execution_and_withdraw_restore(client, tenant, admin_headers, gestor_headers, member, meters):
    [cut] = _order(client, tenant, admin_headers, member, meter_ids=[meters[0].id]).json()
    cancelled = client.post(f"{_admin(tenant)}/cuts/{cut['id']}/cancel", headers=admin_headers)
    assert cancelled.json()["estado"] == "cancelado"
    assert client.post(f"{_admin(tenant)}/cuts/{cut['id']}/cancel", headers=admin_headers).status_code == 409
    assert client.post(f"{_gestor(tenant)}/cuts/{cut['id']}/execute", headers=gestor_headers).status_code == 409

    [cut2] = _order(client, tenant, admin_headers, member, meter_ids=[meters[0].id]).json()
    client.post(f"{_gestor(tenant)}/cuts/{cut2['id']}/execute", headers=gestor_headers)
    client.post(f"{_admin(tenant)}/cuts/{cut2['id']}/order-restore", headers=admin_headers)
    withdrawn = client.post(f"{_admin(tenant)}/cuts/{cut2['id']}/cancel", headers=admin_headers)
    assert withdrawn.json()["estado"] == "ejecutado"


def test_meters_and_members_expose_cut_state(client, tenant, admin_headers, gestor_headers, member, meters):
    [cut] = _order(client, tenant, admin_headers, member, meter_ids=[meters[0].id]).json()

    gestor_meters = {m["codigo"]: m for m in client.get(f"{_gestor(tenant)}/meters", headers=gestor_headers).json()}
    assert gestor_meters["L-1"]["corte_estado"] == "ordenado"
    assert gestor_meters["L-1"]["corte_id"] == cut["id"]
    assert gestor_meters["G-1"]["corte_estado"] is None

    admin_meters = {m["codigo"]: m for m in client.get(f"{_admin(tenant)}/meters", headers=admin_headers).json()}
    assert admin_meters["L-1"]["corte_estado"] == "ordenado"

    [row] = client.get(f"{_admin(tenant)}/members", headers=admin_headers).json()
    assert row["corte_estado"] == "ordenado"


def test_cut_meter_is_left_out_of_new_runs(client, tenant, admin_headers, gestor_headers, member, meters):
    route = client.post(
        f"{_gestor(tenant)}/routes",
        json={"nombre": "R", "meter_ids": [m.id for m in meters]},
        headers=gestor_headers,
    ).json()
    _order(client, tenant, admin_headers, member, meter_ids=[meters[0].id])
    run = client.post(f"{_gestor(tenant)}/routes/{route['id']}/start", headers=gestor_headers).json()
    assert run["total"] == 1
    assert run["siguiente"]["codigo"] == "G-1"


def test_run_in_progress_skips_meter_ordered_cut(client, tenant, admin_headers, gestor_headers, member, meters):
    route = client.post(
        f"{_gestor(tenant)}/routes",
        json={"nombre": "R", "meter_ids": [m.id for m in meters]},
        headers=gestor_headers,
    ).json()
    run = client.post(f"{_gestor(tenant)}/routes/{route['id']}/start", headers=gestor_headers).json()
    assert run["pendientes"] == 2

    _order(client, tenant, admin_headers, member, meter_ids=[meters[0].id])
    run = client.get(f"{_gestor(tenant)}/runs/{run['id']}", headers=gestor_headers).json()
    assert run["salteadas"] == 1
    assert run["pendientes"] == 1
    stops = client.get(f"{_gestor(tenant)}/runs/{run['id']}", headers=gestor_headers).json()
    assert stops["siguiente"]["codigo"] == "G-1"


def test_run_completes_when_all_pending_meters_are_cut(client, tenant, admin_headers, gestor_headers, member, meters):
    route = client.post(
        f"{_gestor(tenant)}/routes",
        json={"nombre": "R", "meter_ids": [m.id for m in meters]},
        headers=gestor_headers,
    ).json()
    run = client.post(f"{_gestor(tenant)}/routes/{route['id']}/start", headers=gestor_headers).json()
    _order(client, tenant, admin_headers, member)
    run = client.get(f"{_gestor(tenant)}/runs/{run['id']}", headers=gestor_headers).json()
    assert run["status"] == "completado"


def test_cuts_are_tenant_scoped(client, tenant, admin_headers, member, meters, db_session):
    [cut] = _order(client, tenant, admin_headers, member, meter_ids=[meters[0].id]).json()
    from app.models import Tenant

    other = Tenant(slug="otra", name="Otra")
    db_session.add(other)
    db_session.commit()
    other_admin = AdminUser(tenant_id=other.id, email="o@o.test", hashed_password=hash_password("x" * 8))
    db_session.add(other_admin)
    db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(other_admin.id, other.id)}"}
    assert client.post(f"{_admin(other)}/cuts/{cut['id']}/cancel", headers=headers).status_code == 404
    assert client.get(f"{_admin(other)}/cuts", headers=headers).json() == []


def test_admin_lists_cuts_filtered(client, tenant, admin_headers, member, meters):
    _order(client, tenant, admin_headers, member)
    all_cuts = client.get(f"{_admin(tenant)}/cuts", headers=admin_headers).json()
    assert len(all_cuts) == 2
    assert client.get(f"{_admin(tenant)}/cuts?estado=ejecutado", headers=admin_headers).json() == []
    assert len(client.get(f"{_admin(tenant)}/cuts?member_id={member.id}", headers=admin_headers).json()) == 2


def test_deleting_a_member_deletes_their_cuts(client, tenant, admin_headers, member, meters, db_session):
    _order(client, tenant, admin_headers, member)
    assert db_session.query(ServiceCut).count() == 2
    resp = client.delete(f"{_admin(tenant)}/members/{member.id}", headers=admin_headers)
    assert resp.status_code == 200
    db_session.expire_all()
    assert db_session.query(ServiceCut).count() == 0
