import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token, create_gestor_access_token, create_platform_token, hash_password
from app.database import Base, get_db
from app.main import app
from app.models import AdminUser, Gestor, ImportBatch, Invoice, Member, Meter, PlatformUser, Tenant
from app.rate_limit import limiter


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    limiter.reset()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def tenant(db_session):
    t = Tenant(slug="coopera-test", name="Cooperativa de Prueba")
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


@pytest.fixture()
def admin(db_session, tenant):
    a = AdminUser(
        tenant_id=tenant.id,
        email="admin@coopera.test",
        hashed_password=hash_password("secret123"),
    )
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


@pytest.fixture()
def admin_token(admin):
    return create_access_token(admin.id, admin.tenant_id)


@pytest.fixture()
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture()
def platform_user(db_session):
    p = PlatformUser(email="dev@coopera.test", hashed_password=hash_password("devsecret"))
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture()
def platform_token(platform_user):
    return create_platform_token(platform_user.id)


@pytest.fixture()
def platform_headers(platform_token):
    return {"Authorization": f"Bearer {platform_token}"}


@pytest.fixture()
def member(db_session, tenant):
    m = Member(
        tenant_id=tenant.id,
        numero_socio="1001",
        nombre="Juana Perez",
        identificador="30111222",
        email="juana@example.com",
    )
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)
    return m


@pytest.fixture()
def gestor(db_session, tenant):
    if tenant.gestor_shared_password_hash is None:
        tenant.gestor_shared_password_hash = hash_password("gestorsecret")
        db_session.commit()
    g = Gestor(
        tenant_id=tenant.id,
        nombre="Carlos Gestor",
        email="carlos@coopera.test",
    )
    db_session.add(g)
    db_session.commit()
    db_session.refresh(g)
    return g


@pytest.fixture()
def gestor_token(gestor):
    return create_gestor_access_token(gestor.id, gestor.tenant_id)


@pytest.fixture()
def gestor_headers(gestor_token):
    return {"Authorization": f"Bearer {gestor_token}"}


@pytest.fixture()
def meter(db_session, tenant, member):
    m = Meter(tenant_id=tenant.id, member_id=member.id, codigo="MED-001", tipo="luz")
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)
    return m


@pytest.fixture()
def import_batch(db_session, tenant):
    b = ImportBatch(tenant_id=tenant.id, period_year=2026, period_month=1, filename="t.csv", row_count=1)
    db_session.add(b)
    db_session.commit()
    db_session.refresh(b)
    return b


@pytest.fixture()
def invoice(db_session, tenant, member, import_batch):
    inv = Invoice(
        tenant_id=tenant.id,
        member_id=member.id,
        import_batch_id=import_batch.id,
        period_year=2026,
        period_month=1,
        consumo=120.5,
        monto=4500.0,
        vencimiento=dt.date(2026, 2, 10),
        pagado=False,
    )
    db_session.add(inv)
    db_session.commit()
    db_session.refresh(inv)
    return inv
