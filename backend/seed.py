"""Seed demo data: one tenant (cooperativa), an admin, and a first
period of invoices so the public lookup has something to show immediately.

Run with: python seed.py
"""
from app.auth import hash_password
from app.database import Base, SessionLocal, engine
from app.models import PlatformUser
from app.services.demo_seed import TENANTS, seed_tenant

Base.metadata.create_all(bind=engine)

db = SessionLocal()


def run():
    if not db.query(PlatformUser).filter(PlatformUser.email == "dev@coopera.app").first():
        db.add(
            PlatformUser(
                email="dev@coopera.app",
                hashed_password=hash_password("coopera-dev123"),
            )
        )

    for t in TENANTS:
        seed_tenant(db, t)

    db.commit()
    print("Seed listo.")
    print("Tenants: " + ", ".join(t["slug"] for t in TENANTS))
    print("Admin login: admin@valleverde.coop / coopera123")
    print("Socio demo: numero_socio=201, identificador=29888777 (valle-verde)")
    print("Dev login: dev@coopera.app / coopera-dev123")
    print("Gestor demo (app mobile): clave compartida del dispositivo = gestor123 (tenant=valle-verde)")
    print(f"  -> elegir perfil '{TENANTS[0]['gestor_nombre']}' tras el device-login")
    print(f"Socios cargados: {len(TENANTS[0]['members'])} (morosos: {', '.join(TENANTS[0]['morosos'])})")


if __name__ == "__main__":
    run()
