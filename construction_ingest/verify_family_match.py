"""Verify a downloaded TDS PDF actually matches the family it was fetched for.

Purely local, text-based cross-check - no LLM call needed for this step (it's
cheap enough to be deterministic): does the PDF's own text plausibly mention
the manufacturer and the family/product it's supposed to document?

This exists because families.json already has known mismatches (e.g. one
family's legacy_source_url pointing at a different manufacturer's datasheet
entirely - see the Aircell/Kingspan and James Hardie/rockwool examples found
during review). Third-party/reseller-hosted PDFs carry the same risk, so
every download - not just reseller ones - gets checked before being trusted.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from construction_ingest.local_pdf_parser import extract_pdf_text

ROOT = Path(__file__).resolve().parents[1]

#: Generic words that appear in almost every family name and carry no
#: identifying signal (manufacturer name is checked separately).
_STOPWORDS = {
    "insulation", "accessory", "accessories", "the", "and", "for", "with",
    "batt", "blanket", "board", "panel", "wrap", "tape", "of", "a", "an",
}


def _keywords(text: str, manufacturer: str) -> list[str]:
    """Meaningful words from a family name, with the manufacturer name and
    generic filler stripped out so what's left is the actual product identity
    (e.g. "Bradford Gold Batts" -> ["gold"])."""
    manufacturer_words = set(re.findall(r"[a-z0-9]+", manufacturer.casefold()))
    words = re.findall(r"[a-z0-9]+", text.casefold())
    return [w for w in words if len(w) > 2 and w not in _STOPWORDS and w not in manufacturer_words]


@dataclass
class VerificationResult:
    family_id: str
    manufacturer: str
    family_name: str
    pdf_path: str
    match_status: str  # "confirmed" | "suspected_mismatch" | "unreadable"
    matched_keywords: list[str]
    missing_keywords: list[str]
    manufacturer_mentioned: bool
    detail: str


def verify_family_match(pdf_path: Path, manufacturer: str, family_name: str) -> VerificationResult:
    text = extract_pdf_text(pdf_path)
    if not text:
        return VerificationResult(
            family_id="", manufacturer=manufacturer, family_name=family_name,
            pdf_path=str(pdf_path), match_status="unreadable",
            matched_keywords=[], missing_keywords=[], manufacturer_mentioned=False,
            detail="No extractable text - PDF may be a scanned image; cannot verify automatically.",
        )

    lowered = text.casefold()
    manufacturer_mentioned = manufacturer.casefold() in lowered

    keywords = _keywords(family_name, manufacturer)
    matched = [k for k in keywords if k in lowered]
    missing = [k for k in keywords if k not in lowered]

    if not keywords:
        # Nothing distinctive to check beyond the manufacturer name itself
        # (e.g. a family literally named "<Manufacturer> Accessory").
        status = "confirmed" if manufacturer_mentioned else "suspected_mismatch"
        detail = (
            "Family name has no distinctive keywords beyond the manufacturer; "
            f"manufacturer {'was' if manufacturer_mentioned else 'was NOT'} found in the PDF text."
        )
    else:
        match_ratio = len(matched) / len(keywords)
        if match_ratio >= 0.5 and manufacturer_mentioned:
            status = "confirmed"
            detail = f"{len(matched)}/{len(keywords)} distinctive keyword(s) found, manufacturer mentioned."
        elif match_ratio >= 0.5:
            status = "confirmed"
            detail = f"{len(matched)}/{len(keywords)} distinctive keyword(s) found, but manufacturer name not seen verbatim (may use a brand name instead)."
        else:
            status = "suspected_mismatch"
            detail = f"Only {len(matched)}/{len(keywords)} distinctive keyword(s) found - this PDF may document a different product."

    return VerificationResult(
        family_id="", manufacturer=manufacturer, family_name=family_name,
        pdf_path=str(pdf_path), match_status=status,
        matched_keywords=matched, missing_keywords=missing,
        manufacturer_mentioned=manufacturer_mentioned, detail=detail,
    )


def verify_batch(items: list[dict]) -> list[VerificationResult]:
    """items: list of {family_id, manufacturer, family_name, pdf_path}."""
    results = []
    for item in items:
        result = verify_family_match(Path(item["pdf_path"]), item["manufacturer"], item["family_name"])
        result.family_id = item["family_id"]
        results.append(result)
    return results


def write_report(results: list[VerificationResult], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps([asdict(r) for r in results], indent=2),
        encoding="utf-8",
    )
