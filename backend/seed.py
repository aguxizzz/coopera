"""Seed demo data: one tenant (cooperativa), an admin, and a first
period of invoices so the public lookup has something to show immediately.

Run with: python seed.py
"""
import datetime as dt

from app.auth import hash_password
from app.database import Base, SessionLocal, engine
from app.models import AdminUser, Gestor, ImportBatch, Invoice, Member, Meter, PlatformUser, Tenant

Base.metadata.create_all(bind=engine)

db = SessionLocal()

TENANTS = [
    {
        "slug": "valle-verde",
        "name": "Cooperativa de Servicios Valle Verde",
        "mp_alias": "coop.valleverde.mp",
        "mp_cbu": "0000003100098765432109",
        "mp_titular": "Cooperativa de Servicios Valle Verde Ltda.",
        "primary_color": "#16a34a",
        "admin_email": "admin@valleverde.coop",
        "members": [
            ("201", "Ana Torres", "29888777", 180.0, 21300.0),
            ("202", "Carlos Díaz", "31555666", 132.0, 17400.0),
        ],
        "gestor_email": "gestor@valleverde.coop",
        "gestor_nombre": "Jorge Ramírez",
        "meters": [
            # (numero_socio, codigo, tipo, direccion, unidad)
            ("201", "LUZ-201-01", "luz", "Calle Falsa 123", "kWh"),
            ("202", "LUZ-202-01", "luz", "Av. Siempreviva 742", "kWh"),
        ],
    },
]


def run():
    today = dt.date.today()
    year, month = today.year, today.month

    if not db.query(PlatformUser).filter(PlatformUser.email == "dev@coopera.app").first():
        db.add(
            PlatformUser(
                email="dev@coopera.app",
                hashed_password=hash_password("coopera-dev123"),
            )
        )

    for t in TENANTS:
        tenant = db.query(Tenant).filter(Tenant.slug == t["slug"]).first()
        if tenant is None:
            tenant = Tenant(
                slug=t["slug"],
                name=t["name"],
                mp_alias=t["mp_alias"],
                mp_cbu=t["mp_cbu"],
                mp_titular=t["mp_titular"],
                primary_color=t["primary_color"],
            )
            db.add(tenant)
            db.flush()

        if tenant.gestor_shared_password_hash is None:
            tenant.gestor_shared_password_hash = hash_password("gestor123")

        if not db.query(AdminUser).filter(AdminUser.tenant_id == tenant.id).first():
            db.add(
                AdminUser(
                    tenant_id=tenant.id,
                    email=t["admin_email"],
                    hashed_password=hash_password("coopera123"),
                )
            )

        batch = ImportBatch(
            tenant_id=tenant.id,
            period_year=year,
            period_month=month,
            filename="seed.py",
            row_count=len(t["members"]),
        )
        db.add(batch)
        db.flush()

        for numero, nombre, dni, consumo, monto in t["members"]:
            member = (
                db.query(Member)
                .filter(Member.tenant_id == tenant.id, Member.numero_socio == numero)
                .first()
            )
            if member is None:
                member = Member(
                    tenant_id=tenant.id,
                    numero_socio=numero,
                    nombre=nombre,
                    identificador=dni,
                )
                db.add(member)
                db.flush()

            invoice = (
                db.query(Invoice)
                .filter(
                    Invoice.member_id == member.id,
                    Invoice.period_year == year,
                    Invoice.period_month == month,
                )
                .first()
            )
            if invoice is None:
                invoice = Invoice(
                    tenant_id=tenant.id,
                    member_id=member.id,
                    import_batch_id=batch.id,
                    period_year=year,
                    period_month=month,
                )
                db.add(invoice)
            invoice.consumo = consumo
            invoice.monto = monto
            invoice.vencimiento = today + dt.timedelta(days=15)

        if not db.query(Gestor).filter(Gestor.tenant_id == tenant.id, Gestor.email == t["gestor_email"]).first():
            db.add(
                Gestor(
                    tenant_id=tenant.id,
                    nombre=t["gestor_nombre"],
                    email=t["gestor_email"],
                )
            )

        for numero, codigo, tipo, direccion, unidad in t["meters"]:
            member = (
                db.query(Member)
                .filter(Member.tenant_id == tenant.id, Member.numero_socio == numero)
                .first()
            )
            meter = (
                db.query(Meter)
                .filter(Meter.tenant_id == tenant.id, Meter.codigo == codigo)
                .first()
            )
            if meter is None:
                db.add(
                    Meter(
                        tenant_id=tenant.id,
                        member_id=member.id,
                        codigo=codigo,
                        tipo=tipo,
                        direccion=direccion,
                        unidad=unidad,
                    )
                )

    db.commit()
    print("Seed listo.")
    print("Tenants: " + ", ".join(t["slug"] for t in TENANTS))
    print("Admin login: admin@valleverde.coop / coopera123")
    print("Socio demo: numero_socio=201, identificador=29888777 (valle-verde)")
    print("Dev login: dev@coopera.app / coopera-dev123")
    print("Gestor demo (app mobile): clave compartida del dispositivo = gestor123 (tenant=valle-verde)")
    print(f"  -> elegir perfil '{TENANTS[0]['gestor_nombre']}' tras el device-login")


if __name__ == "__main__":
    run()
