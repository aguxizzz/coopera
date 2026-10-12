import io

import openpyxl
import pytest

from app.models import Invoice, Member, Meter
from app.services.importer import ImportError_, import_spreadsheet


def _csv_bytes(rows: str) -> bytes:
    return rows.encode("utf-8")


def test_import_csv_creates_members_and_invoices(db_session, tenant):
    content = _csv_bytes(
        "numero_socio,nombre,identificador,consumo,monto,vencimiento\n"
        "1001,Juana Perez,30111222,120.5,4500,2026-02-10\n"
    )
    batch, created, updated = import_spreadsheet(db_session, tenant, "socios.csv", content, 2026, 1)

    assert created == 1
    assert updated == 0
    assert batch.row_count == 1

    member = db_session.query(Member).filter(Member.tenant_id == tenant.id).one()
    assert member.nombre == "Juana Perez"
    invoice = db_session.query(Invoice).filter(Invoice.member_id == member.id).one()
    assert invoice.monto == 4500.0
    assert invoice.consumo == 120.5
    assert invoice.vencimiento.isoformat() == "2026-02-10"


def test_import_csv_updates_existing_member_and_invoice(db_session, tenant):
    content = _csv_bytes(
        "numero_socio,nombre,identificador,consumo,monto,vencimiento\n"
        "1001,Juana Perez,30111222,100,4000,2026-01-10\n"
    )
    import_spreadsheet(db_session, tenant, "socios.csv", content, 2026, 1)

    content2 = _csv_bytes(
        "numero_socio,nombre,identificador,consumo,monto,vencimiento\n"
        "1001,Juana P. Actualizada,30111222,150,5000,2026-01-15\n"
    )
    batch, created, updated = import_spreadsheet(db_session, tenant, "socios.csv", content2, 2026, 1)

    assert created == 0
    assert updated == 1

    member = db_session.query(Member).filter(Member.tenant_id == tenant.id).one()
    assert member.nombre == "Juana P. Actualizada"
    invoice = db_session.query(Invoice).filter(Invoice.member_id == member.id).one()
    assert invoice.monto == 5000.0
    assert invoice.consumo == 150.0


def test_import_csv_different_period_creates_second_invoice(db_session, tenant):
    content1 = _csv_bytes(
        "numero_socio,nombre,identificador,consumo,monto\n1001,Juana Perez,30111222,100,4000\n"
    )
    import_spreadsheet(db_session, tenant, "socios.csv", content1, 2026, 1)

    content2 = _csv_bytes(
        "numero_socio,nombre,identificador,consumo,monto\n1001,Juana Perez,30111222,110,4200\n"
    )
    import_spreadsheet(db_session, tenant, "socios.csv", content2, 2026, 2)

    member = db_session.query(Member).filter(Member.tenant_id == tenant.id).one()
    invoices = db_session.query(Invoice).filter(Invoice.member_id == member.id).all()
    assert len(invoices) == 2


def test_import_csv_skips_rows_without_numero_socio(db_session, tenant):
    content = _csv_bytes(
        "numero_socio,nombre,identificador,consumo,monto\n"
        ",Sin Numero,30111222,100,4000\n"
        "1002,Con Numero,30333444,50,2000\n"
    )
    batch, created, updated = import_spreadsheet(db_session, tenant, "socios.csv", content, 2026, 1)
    assert created == 1
    assert db_session.query(Member).filter(Member.tenant_id == tenant.id).count() == 1


def test_import_missing_required_columns_raises(db_session, tenant):
    content = _csv_bytes("numero_socio,nombre\n1001,Juana\n")
    with pytest.raises(ImportError_):
        import_spreadsheet(db_session, tenant, "socios.csv", content, 2026, 1)


def test_import_unsupported_extension_raises(db_session, tenant):
    with pytest.raises(ImportError_):
        import_spreadsheet(db_session, tenant, "socios.txt", b"junk", 2026, 1)


def test_import_handles_comma_decimal_separator(db_session, tenant):
    content = _csv_bytes(
        "numero_socio,nombre,identificador,consumo,monto\n1001,Juana Perez,30111222,\"120,5\",\"4500,75\"\n"
    )
    import_spreadsheet(db_session, tenant, "socios.csv", content, 2026, 1)
    invoice = db_session.query(Invoice).one()
    assert invoice.consumo == 120.5
    assert invoice.monto == 4500.75


def test_import_xlsx(db_session, tenant):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["numero_socio", "nombre", "identificador", "consumo", "monto", "vencimiento"])
    ws.append(["2001", "Carlos Diaz", "30999888", 90, 3200, "15/03/2026"])
    buf = io.BytesIO()
    wb.save(buf)

    batch, created, updated = import_spreadsheet(db_session, tenant, "socios.xlsx", buf.getvalue(), 2026, 3)
    assert created == 1
    invoice = db_session.query(Invoice).one()
    assert invoice.vencimiento.isoformat() == "2026-03-15"


def test_import_xlsx_empty_file_raises(db_session, tenant):
    wb = openpyxl.Workbook()
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(ImportError_):
        import_spreadsheet(db_session, tenant, "socios.xlsx", buf.getvalue(), 2026, 3)


SOCIOS_CSV = "numero_socio,nombre,identificador,consumo,monto\n1001,Juana Perez,30111222,100,4000\n"


def test_import_creates_one_meter_per_measured_service(db_session, tenant):
    tenant.servicios_medidos = ["luz", "agua"]
    db_session.commit()

    import_spreadsheet(db_session, tenant, "socios.csv", _csv_bytes(SOCIOS_CSV), 2026, 1)

    meters = db_session.query(Meter).filter(Meter.tenant_id == tenant.id).order_by(Meter.tipo).all()
    assert [(m.codigo, m.tipo, m.unidad) for m in meters] == [("1001-agua", "agua", "m3"), ("1001-luz", "luz", "kWh")]
    assert {m.member.numero_socio for m in meters} == {"1001"}


def test_reimport_does_not_duplicate_meters_and_covers_existing_members(db_session, tenant, member):
    # `member` (1001) ya existía, sin medidor, antes de declarar el servicio.
    tenant.servicios_medidos = ["agua"]
    db_session.commit()

    import_spreadsheet(db_session, tenant, "socios.csv", _csv_bytes(SOCIOS_CSV), 2026, 1)
    import_spreadsheet(db_session, tenant, "socios.csv", _csv_bytes(SOCIOS_CSV), 2026, 2)

    meters = db_session.query(Meter).filter(Meter.tenant_id == tenant.id).all()
    assert [(m.codigo, m.member_id) for m in meters] == [("1001-agua", member.id)]


def test_import_keeps_the_meter_a_member_already_has_for_the_service(db_session, tenant, meter):
    tenant.servicios_medidos = ["luz"]
    db_session.commit()

    import_spreadsheet(db_session, tenant, "socios.csv", _csv_bytes(SOCIOS_CSV), 2026, 1)

    assert [m.codigo for m in db_session.query(Meter).filter(Meter.tenant_id == tenant.id)] == ["MED-001"]


def test_import_without_measured_services_creates_no_meters(db_session, tenant):
    import_spreadsheet(db_session, tenant, "socios.csv", _csv_bytes(SOCIOS_CSV), 2026, 1)

    assert db_session.query(Meter).count() == 0


DETALLE_CSV = (
    "numero_socio,nombre,identificador,consumo,monto,direccion,consumo_inicial\n"
    "1001,Juana Perez,30111222,100,4000,San Martin 120,\"1500,5\"\n"
    "1002,Pedro Gomez,30111333,80,3000,,\n"
)


def test_import_loads_direccion_and_consumo_inicial_on_the_service_meter(db_session, tenant):
    tenant.servicios_medidos = ["luz"]
    db_session.commit()

    import_spreadsheet(db_session, tenant, "socios.csv", _csv_bytes(DETALLE_CSV), 2026, 1)

    meters = db_session.query(Meter).order_by(Meter.codigo).all()
    assert [(m.codigo, m.direccion, m.lectura_inicial) for m in meters] == [
        ("1001-luz", "San Martin 120", 1500.5),
        ("1002-luz", None, None),
    ]

    # Una planilla posterior sin esos datos no borra los que ya están.
    import_spreadsheet(db_session, tenant, "socios.csv", _csv_bytes(SOCIOS_CSV), 2026, 2)
    meter = db_session.query(Meter).filter(Meter.codigo == "1001-luz").one()
    assert (meter.direccion, meter.lectura_inicial) == ("San Martin 120", 1500.5)


def test_import_detail_columns_leave_additional_meters_alone(db_session, tenant, member, meter):
    tenant.servicios_medidos = ["luz"]
    otro = Meter(tenant_id=tenant.id, member_id=member.id, codigo="MED-002", tipo="luz", adicional=True, direccion="Campo")
    db_session.add(otro)
    db_session.commit()

    import_spreadsheet(db_session, tenant, "socios.csv", _csv_bytes(DETALLE_CSV), 2026, 1)

    assert (meter.direccion, meter.lectura_inicial) == ("San Martin 120", 1500.5)
    assert (otro.direccion, otro.lectura_inicial) == ("Campo", None)


def test_import_with_several_services_takes_one_consumo_inicial_per_service(db_session, tenant):
    tenant.servicios_medidos = ["luz", "agua"]
    db_session.commit()

    with pytest.raises(ImportError_, match="consumo_inicial_luz, consumo_inicial_agua"):
        import_spreadsheet(db_session, tenant, "socios.csv", _csv_bytes(DETALLE_CSV), 2026, 1)

    content = _csv_bytes(
        "numero_socio,nombre,identificador,consumo,monto,direccion,consumo_inicial_luz,consumo_inicial_agua\n"
        "1001,Juana Perez,30111222,100,4000,San Martin 120,1500,32\n"
    )
    import_spreadsheet(db_session, tenant, "socios.csv", content, 2026, 1)

    meters = db_session.query(Meter).order_by(Meter.tipo).all()
    assert [(m.tipo, m.direccion, m.lectura_inicial) for m in meters] == [
        ("agua", "San Martin 120", 32),
        ("luz", "San Martin 120", 1500),
    ]


def test_import_rejects_a_bad_consumo_inicial_without_loading_anything(db_session, tenant):
    tenant.servicios_medidos = ["luz"]
    db_session.commit()
    content = _csv_bytes(
        "numero_socio,nombre,identificador,consumo,monto,consumo_inicial\n"
        "1001,Juana Perez,30111222,100,4000,1500\n"
        "1002,Pedro Gomez,30111333,80,3000,mil\n"
    )

    with pytest.raises(ImportError_, match="Fila 3: el consumo inicial «mil» no es un número"):
        import_spreadsheet(db_session, tenant, "socios.csv", content, 2026, 1)

    assert db_session.query(Member).count() == 0
    assert db_session.query(Meter).count() == 0
