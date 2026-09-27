from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Columns added after the initial prototype. There's no migrations tool set up
# yet, so on startup we add any that are missing from an existing database
# instead of requiring a fresh one every time the schema grows.
_NEW_TENANT_COLUMNS = {
    "contact_email": "VARCHAR(255)",
    "contact_phone": "VARCHAR(64)",
    "contact_whatsapp": "VARCHAR(64)",
    "contact_address": "VARCHAR(255)",
    "logo_primary_url": "VARCHAR(500)",
    "logo_secondary_url": "VARCHAR(500)",
}


def run_simple_migrations():
    inspector = inspect(engine)
    if "tenants" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("tenants")}
    with engine.begin() as conn:
        for name, coltype in _NEW_TENANT_COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE tenants ADD COLUMN {name} {coltype}"))
