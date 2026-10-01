import io

import openpyxl
import pytest

from app.models import Invoice, Member
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
