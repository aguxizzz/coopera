import io

import openpyxl
import pytest

from app.models import Member, Meter
from app.services.importer import ImportError_
from app.services.meter_importer import import_meters
from app.services.readings import register_reading

HEADER = "numero_socio,nombre,identificador,medidor,tipo,direccion,unidad,lectura_inicial\n"


def _csv(rows: str) -> bytes:
    return (HEADER + rows).encode("utf-8")


def test_import_creates_socios_and_meters(db_session, tenant):
    outcome = import_meters(
        db_session,
        tenant,
        "padron.csv",
        _csv(
            "1001,Juana Perez,30111222,MED-10,luz,San Martín 123,,1500\n"
            "1001,Juana Perez,30111222,MED-11,agua,San Martín 123,,\n"
            "1002,Pedro Gomez,,MED-20,gas,Belgrano 45,m3,\"320,5\"\n"
        ),
    )

    assert (outcome.rows_processed, outcome.meters_created, outcome.meters_updated) == (3, 3, 0)
    assert outcome.members_created == 2
    assert outcome.errors == []
    meters = {m.codigo: m for m in db_session.query(Meter).filter(Meter.tenant_id == tenant.id)}
    assert meters["MED-10"].member.nombre == "Juana Perez"
    assert meters["MED-10"].unidad == "kWh"
    assert meters["MED-10"].lectura_inicial == 1500
    assert meters["MED-10"].direccion == "San Martín 123"
    assert meters["MED-11"].unidad == "m3"
    assert meters["MED-11"].lectura_inicial is None
    assert meters["MED-11"].member_id == meters["MED-10"].member_id
    assert meters["MED-20"].lectura_inicial == 320.5


def test_import_again_updates_instead_of_duplicating(db_session, tenant):
    import_meters(db_session, tenant, "padron.csv", _csv("1001,Juana Perez,,MED-10,luz,San Martín 123,,1500\n"))

    outcome = import_meters(
        db_session,
        tenant,
        "padron.csv",
        # Columnas vacías no pisan lo que ya estaba cargado.
        _csv("1001,Juana P. de Gomez,,MED-10,,,,\n1001,,,MED-12,agua,,,\n"),
    )

    assert (outcome.meters_created, outcome.meters_updated, outcome.members_created) == (1, 1, 0)
    assert db_session.query(Member).filter(Member.tenant_id == tenant.id).count() == 1
    meter = db_session.query(Meter).filter(Meter.codigo == "MED-10").one()
    assert meter.member.nombre == "Juana P. de Gomez"
    assert meter.direccion == "San Martín 123"
    assert meter.lectura_inicial == 1500


def test_import_reports_bad_rows_and_loads_the_rest(db_session, tenant, member, meter):
    outcome = import_meters(
        db_session,
        tenant,
        "padron.csv",
        _csv(
            "2001,Ana Ruiz,,MED-30,vapor,,,\n"
            "2002,,,MED-31,luz,,,\n"
            "2003,Luis Paz,,MED-32,luz,,,abc\n"
            "2004,Eva Sosa,,MED-33,luz,,,\n"
            "2005,Otro Socio,,MED-33,luz,,,\n"
            f"2006,Otro Socio,,{meter.codigo},luz,,,\n"
            ",,,,,,,\n"
        ),
    )

    assert outcome.rows_processed == 6
    assert outcome.meters_created == 1
    assert outcome.members_created == 1
    assert [e.split(":")[0] for e in outcome.errors] == ["Fila 2", "Fila 3", "Fila 4", "Fila 6", "Fila 7"]
    assert "vapor" in outcome.errors[0]
    assert "falta su nombre" in outcome.errors[1]
    assert "no es un número" in outcome.errors[2]
    assert "repetido" in outcome.errors[3]
    assert member.numero_socio in outcome.errors[4]
    # Una fila rechazada no deja a su socio creado a medias.
    numeros = {m.numero_socio for m in db_session.query(Member).filter(Member.tenant_id == tenant.id)}
    assert numeros == {member.numero_socio, "2004"}


def test_import_xlsx_reads_numeric_codes_without_decimals(db_session, tenant):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Numero_Socio", "Nombre", "Medidor", "Lectura_Inicial"])
    ws.append([1001.0, "Juana Perez", 554433.0, 1200])
    buffer = io.BytesIO()
    wb.save(buffer)

    outcome = import_meters(db_session, tenant, "padron.xlsx", buffer.getvalue())

    assert outcome.meters_created == 1
    meter = db_session.query(Meter).filter(Meter.tenant_id == tenant.id).one()
    assert meter.codigo == "554433"
    assert meter.member.numero_socio == "1001"
    assert meter.lectura_inicial == 1200


def test_import_requires_the_base_columns(db_session, tenant):
    with pytest.raises(ImportError_, match="medidor"):
        import_meters(db_session, tenant, "padron.csv", b"numero_socio,nombre\n1001,Juana\n")


def test_first_reading_computes_consumo_against_the_initial_one(db_session, tenant):
    import_meters(db_session, tenant, "padron.csv", _csv("1001,Juana Perez,,MED-10,luz,,,1500\n"))
    meter = db_session.query(Meter).filter(Meter.codigo == "MED-10").one()

    reading = register_reading(db_session, meter, 1620)

    assert reading.valor_anterior == 1500
    assert reading.consumo == 120
    assert reading.anomala is False
    assert register_reading(db_session, meter, 1600).anomala is True


def test_import_endpoint_and_single_meter_form(client, tenant, admin_headers, gestor_headers, member):
    resp = client.post(
        f"/api/t/{tenant.slug}/admin/meters/import",
        headers=admin_headers,
        files={"file": ("padron.csv", _csv("7001,Juana Perez,,MED-10,luz,,,1500\n7002,,,MED-11,luz,,,\n"), "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert (body["meters_created"], body["members_created"], len(body["errors"])) == (1, 1, 1)

    url = f"/api/t/{tenant.slug}/admin/meters"
    created = client.post(
        url,
        headers=admin_headers,
        json={"numero_socio": "3001", "nombre": "Socio Nuevo", "codigo": "MED-50", "tipo": "agua", "lectura_inicial": 80},
    )
    assert created.status_code == 200
    assert created.json()["nombre_socio"] == "Socio Nuevo"
    assert created.json()["unidad"] == "m3"
    assert created.json()["lectura_inicial"] == 80

    existing = client.post(url, headers=admin_headers, json={"member_id": member.id, "codigo": "MED-51"})
    assert existing.status_code == 200
    assert existing.json()["numero_socio"] == member.numero_socio

    assert client.post(url, headers=admin_headers, json={"member_id": member.id, "codigo": "MED-51"}).status_code == 400
    assert client.post(url, headers=admin_headers, json={"codigo": "MED-52"}).status_code == 400
    missing_name = client.post(url, headers=admin_headers, json={"numero_socio": "9999", "codigo": "MED-53"})
    assert missing_name.status_code == 400
    assert missing_name.json()["detail"].startswith("El socio 9999 no existe")

    # La app del gestor ve la lectura inicial como valor anterior, sin que el
    # medidor figure como leído.
    meters = client.get(f"/api/t/{tenant.slug}/gestor/meters", headers=gestor_headers).json()
    nuevo = next(m for m in meters if m["codigo"] == "MED-50")
    assert nuevo["ultima_lectura"] == 80
    assert nuevo["ultima_lectura_fecha"] is None


def test_padron_gives_the_real_number_to_an_auto_created_meter(db_session, tenant, member):
    tenant.servicios_medidos = ["agua"]
    db_session.commit()
    from app.services.service_meters import ensure_service_meters

    ensure_service_meters(db_session, tenant, member)
    db_session.commit()
    provisorio = db_session.query(Meter).filter(Meter.member_id == member.id).one()
    assert provisorio.codigo == "1001-agua"

    # Sin columna de tipo: el medidor es del servicio de la cooperativa.
    content = "numero_socio,nombre,medidor,lectura_inicial\n1001,Juana Perez,A-5532,120\n".encode()
    outcome = import_meters(db_session, tenant, "padron.csv", content)

    assert outcome.errors == []
    meter = db_session.query(Meter).filter(Meter.member_id == member.id).one()
    assert (meter.id, meter.codigo, meter.tipo, meter.lectura_inicial) == (provisorio.id, "A-5532", "agua", 120)


def test_padron_rejects_a_second_meter_of_the_same_service(db_session, tenant, member, meter):
    outcome = import_meters(db_session, tenant, "padron.csv", _csv("1001,Juana Perez,,MED-002,luz,,,\n"))

    assert outcome.meters_created == 0
    assert outcome.errors == [
        "Fila 2: el socio 1001 ya tiene un medidor de luz (MED-001); "
        "si este es de otra propiedad, cargalo como adicional"
    ]
    assert db_session.query(Meter).filter(Meter.member_id == member.id).count() == 1


def test_padron_accepts_a_second_meter_marked_adicional(db_session, tenant, member, meter):
    content = (
        "numero_socio,nombre,medidor,tipo,direccion,adicional\n"
        "1001,Juana Perez,MED-002,luz,Ruta 5 km 3,si\n"
        # Sin principal de agua, "adicional" no aplica: es el medidor del socio.
        "1001,Juana Perez,AG-001,agua,,si\n"
    ).encode()
    outcome = import_meters(db_session, tenant, "padron.csv", content)

    assert outcome.errors == []
    meters = db_session.query(Meter).filter(Meter.member_id == member.id).order_by(Meter.codigo).all()
    assert [(m.codigo, m.tipo, m.adicional) for m in meters] == [
        ("AG-001", "agua", False),
        ("MED-001", "luz", False),
        ("MED-002", "luz", True),
    ]
    # Volver a subirla no lo duplica ni lo rechaza.
    assert import_meters(db_session, tenant, "padron.csv", content).errors == []
    assert db_session.query(Meter).filter(Meter.member_id == member.id).count() == 3


def test_single_meter_form_takes_adicional(client, tenant, admin_headers, member, meter):
    url = f"/api/t/{tenant.slug}/admin/meters"
    payload = {"member_id": member.id, "codigo": "MED-002", "tipo": "luz"}

    assert client.post(url, headers=admin_headers, json=payload).status_code == 400
    created = client.post(url, headers=admin_headers, json={**payload, "adicional": True})
    assert created.status_code == 200
    assert created.json()["adicional"] is True


def test_padron_completes_the_other_services_of_a_new_socio(db_session, tenant):
    tenant.servicios_medidos = ["luz", "agua"]
    db_session.commit()

    outcome = import_meters(db_session, tenant, "padron.csv", _csv("1001,Juana Perez,,MED-10,luz,,,\n"))

    assert outcome.errors == []
    assert sorted(m.codigo for m in db_session.query(Meter)) == ["1001-agua", "MED-10"]
