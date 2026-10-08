from app.auth import create_gestor_access_token
from app.models import Gestor, Meter, Reading, Route, ServiceCut, Tenant
from app.services.demo_seed import TENANTS, seed_tenant


def _demo_gestor(db_session):
    seed = TENANTS[0]
    tenant = seed_tenant(db_session, seed)
    db_session.commit()
    gestor = db_session.query(Gestor).filter(Gestor.email == seed["gestor_email"]).one()
    headers = {"Authorization": f"Bearer {create_gestor_access_token(gestor.id, tenant.id)}"}
    return tenant, gestor, headers


def test_reset_restores_demo_data(client, db_session):
    tenant, gestor, headers = _demo_gestor(db_session)
    meters_before = db_session.query(Meter).filter(Meter.tenant_id == tenant.id).count()
    readings_before = db_session.query(Reading).filter(Reading.tenant_id == tenant.id).count()

    meter = db_session.query(Meter).filter(Meter.tenant_id == tenant.id).first()
    db_session.add(Reading(tenant_id=tenant.id, meter_id=meter.id, gestor_id=gestor.id, valor=99999.0))
    db_session.add(Route(tenant_id=tenant.id, nombre="Ruta de prueba"))
    meter.activo = False
    db_session.commit()

    resp = client.post(f"/api/t/{tenant.slug}/gestor/demo/reset", headers=headers)
    assert resp.status_code == 204

    db_session.expire_all()
    assert db_session.query(Meter).filter(Meter.tenant_id == tenant.id).count() == meters_before
    assert db_session.query(Reading).filter(Reading.tenant_id == tenant.id).count() == readings_before
    assert db_session.query(Route).filter(Route.tenant_id == tenant.id).count() == 0
    assert all(m.activo for m in db_session.query(Meter).filter(Meter.tenant_id == tenant.id))
    # El gestor que dispara el reset sigue pudiendo usar su sesión.
    assert client.get(f"/api/t/{tenant.slug}/gestor/meters", headers=headers).status_code == 200


def test_reset_rejected_outside_demo_tenant(client, db_session, tenant, gestor):
    headers = {"Authorization": f"Bearer {create_gestor_access_token(gestor.id, tenant.id)}"}
    resp = client.post(f"/api/t/{tenant.slug}/gestor/demo/reset", headers=headers)
    assert resp.status_code == 403
    assert db_session.query(Tenant).filter(Tenant.slug == tenant.slug).count() == 1


def test_reset_requires_gestor_token(client, db_session):
    tenant, _, _ = _demo_gestor(db_session)
    assert client.post(f"/api/t/{tenant.slug}/gestor/demo/reset").status_code in (401, 403)


def test_reset_clears_service_cuts(client, db_session):
    tenant, gestor, headers = _demo_gestor(db_session)
    meter = db_session.query(Meter).filter(Meter.tenant_id == tenant.id).first()
    db_session.add(
        ServiceCut(
            tenant_id=tenant.id, member_id=meter.member_id, meter_id=meter.id, motivo="impago", ordenado_por_email="a@b.c"
        )
    )
    db_session.commit()

    assert client.post(f"/api/t/{tenant.slug}/gestor/demo/reset", headers=headers).status_code == 204
    db_session.expire_all()
    assert db_session.query(ServiceCut).filter(ServiceCut.tenant_id == tenant.id).count() == 0
