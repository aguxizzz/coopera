"""Datos y lógica de la cooperativa demo (valle-verde). Los comparten
`seed.py` (carga inicial) y el reset de demo del gestor, que vuelve la
cooperativa a este estado."""
import datetime as dt

from app.auth import hash_password
from app.models import AdminUser, Gestor, ImportBatch, Invoice, Member, Meter, Reading, Tenant


def shift_period(year, month, delta):
    """Month arithmetic helper: delta can be negative to go back periods."""
    idx = (year * 12 + (month - 1)) + delta
    return idx // 12, idx % 12 + 1


TENANTS = [
    {
        "slug": "valle-verde",
        "name": "Cooperativa de Servicios Valle Verde",
        "mp_alias": "coop.valleverde.mp",
        "mp_cbu": "0000003100098765432109",
        "mp_titular": "Cooperativa de Servicios Valle Verde Ltda.",
        "primary_color": "#16a34a",
        "admin_email": "admin@valleverde.coop",
        # (numero_socio, nombre, dni, email, consumo, monto)
        "members": [
            ("201", "Ana Torres", "29888777", None, 180.0, 21300.0),
            ("202", "Carlos Díaz", "31555666", None, 132.0, 17400.0),
            ("203", "María González", "29111222", "maria.gonzalez@example.com", 95.0, 12400.0),
            ("204", "Luis Fernández", "30222333", None, 210.0, 24800.0),
            ("205", "Sofía Martínez", "31333444", "sofia.martinez@example.com", 150.0, 18600.0),
            ("206", "Jorge Pérez", "28444555", None, 310.0, 35200.0),
            ("207", "Lucía Rodríguez", "32555666", None, 88.0, 11900.0),
            ("208", "Martín Sánchez", "27666777", "martin.sanchez@example.com", 175.0, 20700.0),
            ("209", "Valentina López", "33777888", None, 60.0, 9400.0),
            ("210", "Diego Romero", "26888999", None, 420.0, 46500.0),
            ("211", "Camila Flores", "34999000", None, 140.0, 17800.0),
            ("212", "Nicolás Acosta", "29000111", "nicolas.acosta@example.com", 199.0, 23100.0),
        ],
        "gestor_email": "gestor@valleverde.coop",
        "gestor_nombre": "Jorge Ramírez",
        "gestores_extra": [
            # (nombre, email, activo)
            ("Patricia Gómez", "gestor2@valleverde.coop", True),
            ("Esteban Quiroga", "exgestor@valleverde.coop", False),
        ],
        # (numero_socio, codigo, tipo, direccion, unidad)
        "meters": [
            ("201", "LUZ-201-01", "luz", "Calle Falsa 123", "kWh"),
            ("202", "LUZ-202-01", "luz", "Av. Siempreviva 742", "kWh"),
            ("203", "LUZ-203-01", "luz", "Mitre 450", "kWh"),
            ("204", "LUZ-204-01", "luz", "Belgrano 88", "kWh"),
            ("204", "AGUA-204-01", "agua", "Belgrano 88", "m3"),
            ("205", "LUZ-205-01", "luz", "San Martín 1210", "kWh"),
            ("206", "LUZ-206-01", "luz", "Rivadavia 300", "kWh"),
            ("207", "LUZ-207-01", "luz", "Sarmiento 975", "kWh"),
            ("207", "AGUA-207-01", "agua", "Sarmiento 975", "m3"),
            ("208", "LUZ-208-01", "luz", "Chacabuco 55", "kWh"),
            ("209", "LUZ-209-01", "luz", "Alem 640", "kWh"),
            ("210", "LUZ-210-01", "luz", "9 de Julio 1500", "kWh"),
            ("210", "GAS-210-01", "gas", "9 de Julio 1500", "m3"),
            ("211", "LUZ-211-01", "luz", "Moreno 212", "kWh"),
            ("212", "LUZ-212-01", "luz", "Lavalle 390", "kWh"),
        ],
        # Socios con deuda atrasada (vencimiento ya pasado y sin pagar), para
        # probar el flujo de "marcar la más antigua impaga como pagada" y las
        # vistas de morosidad. Se cargan 2 períodos atrás.
        "morosos": ["206", "209"],
    },
]


def seed_tenant(db, t, today=None):
    """Crea o completa la cooperativa descrita en `t` (idempotente)."""
    today = today or dt.date.today()
    year, month = today.year, today.month

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

    members_by_numero = {}

    def upsert_member(numero, nombre, dni, email):
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
                email=email,
            )
            db.add(member)
            db.flush()
        members_by_numero[numero] = member
        return member

    def upsert_invoice(member, batch, p_year, p_month, consumo, monto, vencimiento, pagado):
        invoice = (
            db.query(Invoice)
            .filter(
                Invoice.member_id == member.id,
                Invoice.period_year == p_year,
                Invoice.period_month == p_month,
            )
            .first()
        )
        if invoice is None:
            invoice = Invoice(
                tenant_id=tenant.id,
                member_id=member.id,
                import_batch_id=batch.id,
                period_year=p_year,
                period_month=p_month,
            )
            db.add(invoice)
        invoice.consumo = consumo
        invoice.monto = monto
        invoice.vencimiento = vencimiento
        invoice.pagado = pagado
        return invoice

    # --- Período actual: todos los socios, la mayoría al día ---
    current_batch = ImportBatch(
        tenant_id=tenant.id,
        period_year=year,
        period_month=month,
        filename="seed.py",
        row_count=len(t["members"]),
    )
    db.add(current_batch)
    db.flush()

    for numero, nombre, dni, email, consumo, monto in t["members"]:
        member = upsert_member(numero, nombre, dni, email)
        is_moroso = numero in t.get("morosos", [])
        upsert_invoice(
            member,
            current_batch,
            year,
            month,
            consumo,
            monto,
            today + dt.timedelta(days=15),
            pagado=not is_moroso,
        )

    # --- Período anterior: historial, casi todo pagado ---
    prev_year, prev_month = shift_period(year, month, -1)
    prev_batch = ImportBatch(
        tenant_id=tenant.id,
        period_year=prev_year,
        period_month=prev_month,
        filename="seed.py",
        row_count=len(t["members"]),
    )
    db.add(prev_batch)
    db.flush()

    for numero, nombre, dni, email, consumo, monto in t["members"]:
        member = members_by_numero[numero]
        is_moroso = numero in t.get("morosos", [])
        upsert_invoice(
            member,
            prev_batch,
            prev_year,
            prev_month,
            round(consumo * 0.92, 2),
            round(monto * 0.92, 2),
            today - dt.timedelta(days=18),
            pagado=not is_moroso,
        )

    # --- Dos períodos atrás: factura vencida y todavía impaga para los
    # socios morosos, para poder probar deuda acumulada / mora real ---
    old_year, old_month = shift_period(year, month, -2)
    old_batch = ImportBatch(
        tenant_id=tenant.id,
        period_year=old_year,
        period_month=old_month,
        filename="seed.py",
        row_count=len(t.get("morosos", [])),
    )
    db.add(old_batch)
    db.flush()

    for numero in t.get("morosos", []):
        member = members_by_numero[numero]
        base_consumo, base_monto = next(
            (c, m) for n, _, _, _, c, m in t["members"] if n == numero
        )
        upsert_invoice(
            member,
            old_batch,
            old_year,
            old_month,
            round(base_consumo * 0.85, 2),
            round(base_monto * 0.85, 2),
            today - dt.timedelta(days=48),
            pagado=False,
        )

    # --- Gestores ---
    if not db.query(Gestor).filter(Gestor.tenant_id == tenant.id, Gestor.email == t["gestor_email"]).first():
        db.add(
            Gestor(
                tenant_id=tenant.id,
                nombre=t["gestor_nombre"],
                email=t["gestor_email"],
            )
        )
        db.flush()

    for nombre, email, activo in t.get("gestores_extra", []):
        if not db.query(Gestor).filter(Gestor.tenant_id == tenant.id, Gestor.email == email).first():
            db.add(
                Gestor(
                    tenant_id=tenant.id,
                    nombre=nombre,
                    email=email,
                    activo=activo,
                )
            )

    gestor_principal = (
        db.query(Gestor)
        .filter(Gestor.tenant_id == tenant.id, Gestor.email == t["gestor_email"])
        .first()
    )

    # --- Medidores + un historial de 2 lecturas cada uno ---
    meters_by_codigo = {}
    for numero, codigo, tipo, direccion, unidad in t["meters"]:
        member = members_by_numero[numero]
        meter = (
            db.query(Meter)
            .filter(Meter.tenant_id == tenant.id, Meter.codigo == codigo)
            .first()
        )
        if meter is None:
            meter = Meter(
                tenant_id=tenant.id,
                member_id=member.id,
                codigo=codigo,
                tipo=tipo,
                direccion=direccion,
                unidad=unidad,
            )
            db.add(meter)
            db.flush()
        meters_by_codigo[codigo] = meter

    for codigo, meter in meters_by_codigo.items():
        if db.query(Reading).filter(Reading.meter_id == meter.id).first():
            continue
        # Arrancamos de un valor base y acumulamos una lectura anterior
        # y una actual, como quedaría tras dos ciclos reales de lectura.
        base = 1000.0 + (meter.id * 37 % 500)
        consumo_1 = 40.0 + (meter.id % 7) * 5
        consumo_2 = 45.0 + (meter.id % 5) * 6
        valor_0 = base
        valor_1 = base + consumo_1
        valor_2 = valor_1 + consumo_2
        db.add(
            Reading(
                tenant_id=tenant.id,
                meter_id=meter.id,
                gestor_id=gestor_principal.id if gestor_principal else None,
                valor=valor_1,
                valor_anterior=valor_0,
                consumo=consumo_1,
                created_at=dt.datetime.utcnow() - dt.timedelta(days=45),
            )
        )
        db.add(
            Reading(
                tenant_id=tenant.id,
                meter_id=meter.id,
                gestor_id=gestor_principal.id if gestor_principal else None,
                valor=valor_2,
                valor_anterior=valor_1,
                consumo=consumo_2,
                created_at=dt.datetime.utcnow() - dt.timedelta(days=15),
            )
        )
    return tenant
