from io import BytesIO

from pypdf import PdfWriter

from scripts.evidence_triage import issues_for
from scripts.ingest_evidence import extract_candidates


def test_html_extraction_records_region_and_confidence():
    html = b"<html><body><p>Thermal R-value is R2.5 for this product.</p></body></html>"
    candidates, ocr_required = extract_candidates(html, "text/html", "https://example.com/product")
    assert ocr_required is False
    assert candidates[0]["region"] == "HTML text block"
    assert 0 <= candidates[0]["extractor_confidence"] <= 1


def test_image_only_pdf_is_flagged_for_ocr():
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(output)
    candidates, ocr_required = extract_candidates(output.getvalue(), "application/pdf", "https://example.com/scan.pdf")
    assert candidates == []
    assert ocr_required is True


def test_triage_catches_missing_standard_context_and_ocr_confidence():
    item = {"metric_type": "thermal_r", "extractor_confidence": 0.4, "test_context": "", "test_standard": "", "source_locator": "pending", "extraction_method": "ocr", "ocr_confidence": None, "evidence_status": "pending_human_review", "verified_by": None, "verified_at": None}
    issues = issues_for(item)
    assert "low extractor confidence" in issues
    assert "missing test context" in issues
    assert "missing test standard" in issues
    assert "missing OCR confidence" in issues
