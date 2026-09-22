import csv
import datetime as dt
import io

import openpyxl
from sqlalchemy.orm import Session

from app.models import ImportBatch, Invoice, Member, Tenant

REQUIRED_COLUMNS = {"numero_socio", "nombre", "identificador", "consumo", "monto"}


class ImportError_(Exception):
    pass


def _rows_from_csv(content: bytes) -> tuple[list[str], list[dict]]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ImportError_("El archivo no tiene encabezados")
    headers = [h.strip().lower() for h in reader.fieldnames]
    reader.fieldnames = headers
    return headers, list(reader)


def _rows_from_xlsx(content: bytes) -> tuple[list[str], list[dict]]:
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        raise ImportError_("El archivo está vacío")
    headers = [str(h).strip().lower() if h is not None else "" for h in header_row]

    rows = []
    for raw in rows_iter:
        if all(v is None for v in raw):
            continue
        rows.append({headers[i]: raw[i] for i in range(len(headers)) if i < len(raw)})
    return headers, rows


def _read_rows(filename: str, content: bytes) -> tuple[list[str], list[dict]]:
    lower = filename.lower()
    if lower.endswith(".csv"):
        return _rows_from_csv(content)
    if lower.endswith((".xlsx", ".xls")):
        return _rows_from_xlsx(content)
    raise ImportError_("Formato no soportado. Usa un archivo .csv o .xlsx")


def _clean_str(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_float(value) -> float:
    s = _clean_str(value).replace(",", ".")
    if not s or s.lower() == "nan":
        return 0.0
    return float(s)


def _clean_date(value) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    s = _clean_str(value)
    if not s or s.lower() == "nan":
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def import_spreadsheet(
    db: Session,
    tenant: Tenant,
    filename: str,
    content: bytes,
    period_year: int,
    period_month: int,
) -> tuple[ImportBatch, int, int]:
    headers, rows = _read_rows(filename, content)

    missing = REQUIRED_COLUMNS - set(headers)
    if missing:
        raise ImportError_(f"Faltan columnas requeridas: {', '.join(sorted(missing))}")

    batch = ImportBatch(
        tenant_id=tenant.id,
        period_year=period_year,
        period_month=period_month,
        filename=filename,
        row_count=len(rows),
    )
    db.add(batch)
    db.flush()

    created = 0
    updated = 0

    for row in rows:
        numero_socio = _clean_str(row.get("numero_socio"))
        if not numero_socio:
            continue
        nombre = _clean_str(row.get("nombre"))
        identificador = _clean_str(row.get("identificador"))
        consumo = _clean_float(row.get("consumo"))
        monto = _clean_float(row.get("monto"))
        vencimiento = _clean_date(row.get("vencimiento"))

        member = (
            db.query(Member)
            .filter(Member.tenant_id == tenant.id, Member.numero_socio == numero_socio)
            .first()
        )
        if member is None:
            member = Member(
                tenant_id=tenant.id,
                numero_socio=numero_socio,
                nombre=nombre,
                identificador=identificador,
            )
            db.add(member)
            db.flush()
            created += 1
        else:
            member.nombre = nombre
            member.identificador = identificador
            updated += 1

        invoice = (
            db.query(Invoice)
            .filter(
                Invoice.member_id == member.id,
                Invoice.period_year == period_year,
                Invoice.period_month == period_month,
            )
            .first()
        )
        if invoice is None:
            invoice = Invoice(
                tenant_id=tenant.id,
                member_id=member.id,
                import_batch_id=batch.id,
                period_year=period_year,
                period_month=period_month,
            )
            db.add(invoice)

        invoice.consumo = consumo
        invoice.monto = monto
        invoice.vencimiento = vencimiento
        invoice.import_batch_id = batch.id

    db.commit()
    db.refresh(batch)
    return batch, created, updated
