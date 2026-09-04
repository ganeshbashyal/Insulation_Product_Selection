"""Write a reviewer queue for incomplete or low-confidence evidence."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def issues_for(item: dict, low_confidence: float = 0.8) -> list[str]:
    issues = []
    if item.get("extractor_confidence", 0) < low_confidence:
        issues.append("low extractor confidence")
    if not item.get("test_context"):
        issues.append("missing test context")
    if item.get("metric_type") != "product_identity" and not item.get("test_standard"):
        issues.append("missing test standard")
    if "pending" in item.get("source_locator", "").casefold():
        issues.append("source locator pending")
    if item.get("extraction_method") == "ocr" and item.get("ocr_confidence") is None:
        issues.append("missing OCR confidence")
    if item.get("evidence_status") == "verified" and (not item.get("verified_by") or not item.get("verified_at")):
        issues.append("verified without reviewer metadata")
    return issues


def build_report(output: Path) -> int:
    registry = json.loads((ROOT / "knowledge" / "performance_evidence.json").read_text(encoding="utf-8"))
    rows = []
    for family in registry["families"]:
        for item in family["evidence_items"]:
            issues = issues_for(item)
            if issues:
                rows.append({"family_id": family["family_id"], "evidence_id": item["evidence_id"], "evidence_status": item["evidence_status"], "extractor_confidence": item["extractor_confidence"], "issues": "; ".join(issues)})
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["family_id", "evidence_id", "evidence_status", "extractor_confidence", "issues"])
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    destination = ROOT / "reports" / "evidence_triage.csv"
    print(f"Evidence triage items: {build_report(destination)}; report: {destination}")
