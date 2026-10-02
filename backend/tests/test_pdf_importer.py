import io

import pytest
from reportlab.pdfgen import canvas
from sqlalchemy.orm import sessionmaker

from app.models import Invoice, Member, PdfImportJob, PdfImportProfile
from app.services.pdf_importer import PdfProfileError, apply_patterns, preview_profile, run_pdf_import_job

FIELD_PATTERNS = {
    "numero_socio": r"N\. Socio:\s*(\d+)",
    "monto": r"\$([0-9,]+\.[0-9]{2})",
}


def _one_page_pdf(numero_socio: str, monto: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(50, 750, f"N. Socio: {numero_socio}")
    c.drawString(50, 700, f"Subtotal $1.00")
    c.drawString(50, 650, f"Total ${monto}")
    c.showPage()
    c.save()
    return buf.getvalue()


def test_apply_patterns_last_match_wins():
    text = "N. Socio: 42\nSubtotal $1.00\nTotal $1,234.56"
    compiled = {k: __import__("re").compile(v) for k, v in FIELD_PATTERNS.items()}
    fields = apply_patterns(text, compiled)
    assert fields["numero_socio"] == "42"
    assert fields["monto"] == "1234.56"  # thousands-separator comma stripped for downstream float parsing


def test_apply_patterns_missing_field_is_none():
    compiled = {k: __import__("re").compile(v) for k, v in FIELD_PATTERNS.items()}
    fields = apply_patterns("no matches here", compiled)
    assert fields["numero_socio"] is None
    assert fields["monto"] is None


def test_preview_profile_extracts_fields_and_raw_text():
    pdf = _one_page_pdf("42", "1,234.56")
    pages = preview_profile(pdf, FIELD_PATTERNS)
    assert len(pages) == 1
    assert pages[0]["page"] == 1
    assert pages[0]["fields"]["numero_socio"] == "42"
    assert pages[0]["fields"]["monto"] == "1234.56"
    assert "Socio" in pages[0]["raw_text"]


def test_preview_profile_rejects_invalid_regex():
    pdf = _one_page_pdf("42", "1,234.56")
    with pytest.raises(PdfProfileError):
        preview_profile(pdf, {"numero_socio": "("})


@pytest.fixture()
def patched_session_local(monkeypatch, db_session):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_session.get_bind())
    monkeypatch.setattr("app.services.pdf_importer.SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


def test_run_pdf_import_job_creates_member_and_invoice(db_session, tenant, patched_session_local):
    db_session.add(PdfImportProfile(tenant_id=tenant.id, field_patterns=FIELD_PATTERNS))
    job = PdfImportJob(tenant_id=tenant.id, period_year=2026, period_month=3)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    pdf = _one_page_pdf("42", "1,234.56")
    run_pdf_import_job(job.id, [("sector1.pdf", pdf)])

    db_session.expire_all()
    refreshed_job = db_session.get(PdfImportJob, job.id)
    assert refreshed_job.status == "done"
    assert refreshed_job.total_pages == 1
    assert refreshed_job.processed_pages == 1
    assert refreshed_job.import_batch_id is not None

    member = db_session.query(Member).filter(Member.tenant_id == tenant.id, Member.numero_socio == "42").first()
    assert member is not None
    invoice = db_session.query(Invoice).filter(Invoice.member_id == member.id).first()
    assert invoice is not None
    assert float(invoice.monto) == 1234.56


def test_run_pdf_import_job_without_profile_sets_error(db_session, tenant, patched_session_local):
    job = PdfImportJob(tenant_id=tenant.id, period_year=2026, period_month=3)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    run_pdf_import_job(job.id, [("sector1.pdf", _one_page_pdf("42", "1,234.56"))])

    db_session.expire_all()
    refreshed_job = db_session.get(PdfImportJob, job.id)
    assert refreshed_job.status == "error"
    assert "perfil" in refreshed_job.error
