"""PDF socio import: each page of one or more uploaded PDFs is one socio
(same layout as copasel's boletas). Since every cooperativa's PDF layout is
different, the field extraction is driven by a per-tenant `PdfImportProfile`
(field name -> regex with one capture group) authored by a platform dev via
/api/dev after testing it against a sample PDF — see routers/dev.py."""

import io
import re

from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import PdfImportJob, PdfImportProfile, Tenant
from app.services.importer import upsert_rows

PREVIEW_MAX_PAGES = 5
PREVIEW_TEXT_CHARS = 1000

REQUIRED_PROFILE_FIELD = "numero_socio"

# These feed `_clean_float` downstream (app/services/importer.py), which only
# understands a comma as a *decimal* separator (Spanish locale, e.g. "120,5").
# PDFs commonly print money with a comma *thousands* separator instead (e.g.
# copasel's "$1,234.56"), so normalize those before they reach that parser.
AMOUNT_FIELDS = {"consumo", "monto"}


class PdfProfileError(Exception):
    pass


def _normalize_amount(value: str) -> str:
    if "," in value and "." in value:
        return value.replace(",", "")
    return value


def _compile_patterns(field_patterns: dict[str, str]) -> dict[str, re.Pattern]:
    compiled = {}
    for field, pattern in field_patterns.items():
        try:
            compiled[field] = re.compile(pattern)
        except re.error as exc:
            raise PdfProfileError(f"Regex inválida para '{field}': {exc}")
    return compiled


def extract_pages_text(content: bytes) -> list[str]:
    reader = PdfReader(io.BytesIO(content))
    return [page.extract_text() or "" for page in reader.pages]


def apply_patterns(text: str, compiled_patterns: dict[str, re.Pattern]) -> dict[str, str | None]:
    """Last match wins per field (e.g. a boleta often prints a running
    subtotal followed by the real total $ amount — the last one on the
    page is the one that matters, same convention copasel used)."""
    result: dict[str, str | None] = {}
    for field, pattern in compiled_patterns.items():
        matches = pattern.findall(text)
        if not matches:
            result[field] = None
            continue
        last = matches[-1]
        value = last if isinstance(last, str) else last[0]
        if field in AMOUNT_FIELDS:
            value = _normalize_amount(value)
        result[field] = value
    return result


def preview_profile(
    content: bytes, field_patterns: dict[str, str], max_pages: int = PREVIEW_MAX_PAGES
) -> list[dict]:
    """Used by the dev-panel "test" endpoint: shows the raw text and the
    fields a candidate profile would extract, for the first few pages of a
    sample PDF, without touching the DB."""
    compiled = _compile_patterns(field_patterns)
    pages_text = extract_pages_text(content)[:max_pages]
    return [
        {
            "page": i + 1,
            "raw_text": text[:PREVIEW_TEXT_CHARS],
            "fields": apply_patterns(text, compiled),
        }
        for i, text in enumerate(pages_text)
    ]


def run_pdf_import_job(job_id: int, files: list[tuple[str, bytes]]) -> None:
    """Runs as a FastAPI BackgroundTask: opens its own DB session (the
    request's session is closed by the time this runs) and updates the job
    row as it goes so the admin panel can poll progress."""
    db: Session = SessionLocal()
    try:
        job = db.get(PdfImportJob, job_id)
        if job is None:
            return
        tenant = db.get(Tenant, job.tenant_id)
        profile_patterns = _load_profile_patterns(db, tenant)

        job.status = "processing"
        db.commit()

        if profile_patterns is None:
            job.status = "error"
            job.error = "No hay un perfil de import de PDF configurado para esta cooperativa"
            db.commit()
            return

        compiled = _compile_patterns(profile_patterns)
        if REQUIRED_PROFILE_FIELD not in compiled:
            job.status = "error"
            job.error = f"El perfil no tiene un patrón para '{REQUIRED_PROFILE_FIELD}'"
            db.commit()
            return

        pages_per_file = [(filename, extract_pages_text(content)) for filename, content in files]
        total_pages = sum(len(pages) for _, pages in pages_per_file)
        job.total_pages = total_pages
        db.commit()

        rows = []
        processed = 0
        progress_every = 25  # avoid a DB commit per page on large (1000+ page) imports
        for _filename, pages in pages_per_file:
            for text in pages:
                fields = apply_patterns(text, compiled)
                if fields.get(REQUIRED_PROFILE_FIELD):
                    rows.append(fields)
                processed += 1
                if processed % progress_every == 0:
                    job.processed_pages = processed
                    db.commit()
        job.processed_pages = processed
        db.commit()

        filename = ", ".join(f for f, _ in files)
        batch, _created, _updated = upsert_rows(
            db, tenant, filename, rows, job.period_year, job.period_month
        )

        job.import_batch_id = batch.id
        job.status = "done"
        db.commit()
    except Exception as exc:  # noqa: BLE001 - surface any failure on the job row
        db.rollback()
        job = db.get(PdfImportJob, job_id)
        if job is not None:
            job.status = "error"
            job.error = str(exc)
            db.commit()
    finally:
        db.close()


def _load_profile_patterns(db: Session, tenant: Tenant) -> dict[str, str] | None:
    profile = db.query(PdfImportProfile).filter(PdfImportProfile.tenant_id == tenant.id).first()
    return profile.field_patterns if profile else None
