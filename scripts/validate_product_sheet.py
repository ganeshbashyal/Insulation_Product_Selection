"""Validate the current product sheet against family literature with a local LLM.

This is a fully local, read-only audit over the supplied product sheet. It
combines manufacturer, product name, product use, material, SKU/code clues and
family literature to judge whether each row fits the current family mapping.
The local model is only used as an adjudicator over a deterministic shortlist;
it does not write files, approve claims or reach out to any hosted service.

Outputs:
    reports/product_sheet_validation.json
    reports/product_sheet_validation.csv

Usage:
    python scripts/validate_product_sheet.py
    python scripts/validate_product_sheet.py --source data/raw/Product_Master_Bot.xlsx
    python scripts/validate_product_sheet.py --sheet Sheet1 --limit 25
    python scripts/validate_product_sheet.py --resume --retry-failed
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
import hashlib
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_client import OLLAMA_HOST, ollama_available  # noqa: E402
from scripts.build_sku_dataset import get_family_id_for_product, load_families  # noqa: E402


def _discover_source() -> Path:
    home = Path.home()
    candidates = [
        home / "Downloads" / "Product_Master_Bot_SKU_Matched.xlsx",
        home / "Downloads" / "Product_Master_Bot_KB_SKU_Matched.xlsx",
        ROOT / "data" / "raw" / "Product_Master_Bot.xlsx",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


DEFAULT_SOURCE = _discover_source()
DEFAULT_SHEET = None
DEFAULT_MODEL = os.getenv("OLLAMA_PRODUCT_VALIDATE_MODEL", "llama3.2:latest")
DEFAULT_TIMEOUT = float(os.getenv("OLLAMA_PRODUCT_VALIDATE_TIMEOUT", "180"))
OUTPUT_JSON = ROOT / "reports" / "product_sheet_validation.json"
OUTPUT_CSV = ROOT / "reports" / "product_sheet_validation.csv"
OUTPUT_MD = ROOT / "reports" / "product_sheet_family_review.md"
STATE_JSON = ROOT / "data" / "local" / "product_sheet_validation_state.json"
STATE_SCHEMA_VERSION = 2

SYSTEM_PROMPT = """You are a strict local auditor for an insulation product sheet.

You compare a single product-sheet row against existing family literature and
metadata. Use only the supplied evidence. Do not invent facts, do not upgrade
uncertain matches to approvals, and do not suggest public-facing claims.

Return exactly one JSON object with these keys:
  status: supported | ambiguous | mismatch | needs_more_info
  source_family_id: string or null
  best_family_id: string or null
  confidence: integer 0-100
  code_alignment: strong | weak | none
  literature_alignment: strong | partial | conflict
  reasons: array of short strings
  conflicts: array of short strings
  follow_up_questions: array of short strings
  canonical_checks: object with boolean manufacturer, material, product_name, product_code

If the row clearly fits the current family mapping, mark it supported.
If the row points to a different family, mark mismatch.
If the row is close but not definitive, mark ambiguous.
If key evidence is missing, mark needs_more_info.
"""

USER_PROMPT_TEMPLATE = """PRODUCT SHEET ROW:
{row_json}

CURRENT FAMILY HINT:
{hint_json}

TOP CANDIDATE FAMILIES:
{candidates_json}

FAMILY LITERATURE EXCERPT:
{literature_json}

Task:
- Decide whether the current family mapping is supported by the product sheet and literature.
- Use manufacturer, product family name, material, product use and product code/MPN clues.
- Prefer the candidate family whose literature best matches the row.
- Keep the answer grounded in the supplied data; if the code or product description does not match the literature, say so plainly.
"""


def _clean(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    return str(value).strip()


def _load_rows(source: Path, sheet: str | None) -> tuple[pd.DataFrame, str | None]:
    if source.suffix.casefold() == ".csv":
        return pd.read_csv(source, dtype=str).fillna(""), None
    if source.suffix.casefold() in {".xlsx", ".xlsm", ".xls"}:
        selected = sheet
        if selected is None:
            workbook = load_workbook(source, read_only=True, data_only=True)
            try:
                if "Sheet1" in workbook.sheetnames:
                    selected = "Sheet1"
                elif "Product_Master_Bot" in workbook.sheetnames:
                    selected = "Product_Master_Bot"
                else:
                    selected = workbook.sheetnames[0]
            finally:
                workbook.close()
        return pd.read_excel(source, sheet_name=selected, dtype=str).fillna(""), selected
    raise ValueError("Source must be a CSV or Excel workbook")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError:
        return ""


def _load_literature_excerpt(root: Path, family: dict, max_length: int = 1400) -> dict:
    knowledge_file = family.get("knowledge_file")
    if not knowledge_file:
        return {}
    path = root / "knowledge" / family["manufacturer"].casefold() / knowledge_file
    if not path.is_file():
        # Some knowledge files live under a different case/space pattern; do a
        # bounded search for the named file inside the manufacturer directory.
        manufacturer_dir = root / "knowledge" / family["manufacturer"].casefold()
        if manufacturer_dir.is_dir():
            for candidate in manufacturer_dir.rglob(Path(knowledge_file).name):
                if candidate.is_file():
                    path = candidate
                    break
    text = _read_text(path)
    if not text:
        return {}
    return {
        "knowledge_file": path.relative_to(root).as_posix() if path.exists() else knowledge_file,
        "excerpt": text[:max_length],
    }


def _source_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _family_summary(root: Path, family: dict) -> dict:
    summary = {
        "family_id": family["family_id"],
        "name": family.get("name", ""),
        "manufacturer": family.get("manufacturer", ""),
        "category": family.get("category", ""),
        "primary_function": family.get("primary_function", ""),
        "confidence": family.get("confidence", ""),
        "applications": family.get("applications", []),
        "keywords": family.get("keywords", []),
        "questions": family.get("questions", []),
        "human_gates": family.get("human_gates", []),
    }
    summary.update(_load_literature_excerpt(root, family))
    return summary


def _row_payload(row: pd.Series) -> dict:
    return {
        "manufacturer": _clean(row.get("Manufacturer Name")),
        "our_sku": _clean(row.get("Our SKU")),
        "supplier_sku": _clean(row.get("SKU")),
        "product_name": _clean(row.get("Our Product Name")),
        "category": _clean(row.get("Category")),
        "material_type": _clean(row.get("Material Type")),
        "product_use": _clean(row.get("Product Use")),
        "mpn": _clean(row.get("MPN")),
        "validation_status": _clean(row.get("Validation Status")),
        "validation_notes": _clean(row.get("Validation Notes")),
        "bot_content_status": _clean(row.get("Bot Content Status")),
        "source_family_id": _clean(row.get("family_id")),
    }


def _row_signature(payload: dict) -> str:
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return digest


def _model_chat(model: str, system_prompt: str, user_prompt: str, timeout: float) -> str | None:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "think": False,
        "keep_alive": "10m",
        "options": {"temperature": 0, "num_predict": 900, "num_ctx": 8192},
    }
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        print(f"    ! ollama call failed: {exc}", file=sys.stderr)
        return None
    return (data.get("message") or {}).get("content", "").strip() or None


def _parse_json_reply(raw: str) -> dict | None:
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _tokenize(text: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", text.casefold()) if len(token) > 2}


def _extract_code_clues(knowledge: dict) -> set[str]:
    clues = set()
    excerpt = knowledge.get("excerpt", "")
    for code in re.findall(r"\b\d{5,7}\b", excerpt):
        clues.add(code)
    for code in re.findall(r"\b[A-Z]{1,5}\d{2,7}[A-Z0-9-]*\b", excerpt, re.I):
        clues.add(code.upper())
    return clues


def _family_score(payload: dict, family: dict, knowledge: dict) -> int:
    score = 0
    text = " ".join(
        value for value in [
            payload["manufacturer"],
            payload["product_name"],
            payload["category"],
            payload["material_type"],
            payload["product_use"],
            payload["mpn"],
        ] if value
    ).casefold()
    family_text = " ".join(
        value for value in [
            family.get("name", ""),
            family.get("category", ""),
            family.get("primary_function", ""),
            " ".join(family.get("applications", []) or []),
            " ".join(family.get("keywords", []) or []),
            " ".join(family.get("questions", []) or []),
            " ".join(family.get("human_gates", []) or []),
            knowledge.get("excerpt", ""),
        ] if value
    ).casefold()
    if payload["manufacturer"] and payload["manufacturer"].casefold() == family.get("manufacturer", "").casefold():
        score += 4
    row_tokens = _tokenize(text)
    family_tokens = _tokenize(family_text)
    score += len(row_tokens & family_tokens)
    code_clues = _extract_code_clues(knowledge)
    if payload["mpn"] and payload["mpn"].casefold() in {clue.casefold() for clue in code_clues}:
        score += 6
    if payload["our_sku"] and payload["our_sku"].casefold() in family_text:
        score += 2
    if payload["supplier_sku"] and payload["supplier_sku"].casefold() in family_text:
        score += 2
    return score


def _candidate_families(root: Path, families: dict[str, dict], payload: dict, limit: int = 4) -> list[dict]:
    candidates = []
    for family_id, family in families.items():
        knowledge = _family_summary(root, family)
        candidates.append({
            "family_id": family_id,
            "score": _family_score(payload, family, knowledge),
            "summary": knowledge,
        })
    candidates.sort(key=lambda item: (-item["score"], item["summary"]["manufacturer"], item["family_id"]))
    return candidates[:limit]


def _audit_row(root: Path, row: pd.Series, families: dict[str, dict], model: str, timeout: float) -> dict:
    payload = _row_payload(row)
    deterministic_family_id = ""
    if payload["manufacturer"]:
        try:
            deterministic_family_id = get_family_id_for_product(row, payload["manufacturer"], families)
        except Exception:
            deterministic_family_id = ""
    current_family_id = payload["source_family_id"] or deterministic_family_id
    candidate_families = _candidate_families(root, families, payload)
    candidate_ids = [item["family_id"] for item in candidate_families]
    if current_family_id and current_family_id not in candidate_ids and current_family_id in families:
        candidate_families.append({
            "family_id": current_family_id,
            "score": 10_000,
            "summary": _family_summary(root, families[current_family_id]),
        })
        candidate_ids = [item["family_id"] for item in candidate_families]
    literature = {item["family_id"]: item["summary"] for item in candidate_families}
    prompt = USER_PROMPT_TEMPLATE.format(
        row_json=json.dumps(payload, ensure_ascii=False, indent=2),
        hint_json=json.dumps({
            "deterministic_family_id": deterministic_family_id,
            "current_family_id": current_family_id,
            "candidate_ids": candidate_ids,
        }, ensure_ascii=False, indent=2),
        candidates_json=json.dumps(candidate_families, ensure_ascii=False, indent=2),
        literature_json=json.dumps(literature, ensure_ascii=False, indent=2),
    )
    raw = _model_chat(model, SYSTEM_PROMPT, prompt, timeout)
    if not raw:
        return {
            **payload,
            "sku_record_id": _clean(row.get("sku_record_id")),
            "source_signature": _row_signature(payload),
            "deterministic_family_id": deterministic_family_id,
            "status": "model_failed",
            "best_family_id": None,
            "confidence": None,
            "code_alignment": "none",
            "literature_alignment": "partial",
            "reasons": ["Local model unavailable or timed out."],
            "conflicts": [],
            "follow_up_questions": [],
        }
    parsed = _parse_json_reply(raw)
    if parsed is None:
        return {
            **payload,
            "sku_record_id": _clean(row.get("sku_record_id")),
            "source_signature": _row_signature(payload),
            "deterministic_family_id": deterministic_family_id,
            "status": "model_reply_unparseable",
            "best_family_id": None,
            "confidence": None,
            "code_alignment": "none",
            "literature_alignment": "partial",
            "reasons": ["Local model reply could not be parsed as JSON."],
            "conflicts": [],
            "follow_up_questions": [],
        }
    status = parsed.get("status") or "needs_more_info"
    confidence = parsed.get("confidence")
    if isinstance(confidence, str) and confidence.isdigit():
        confidence = int(confidence)
    elif not isinstance(confidence, int):
        confidence = None
    result = {
        **payload,
        "sku_record_id": _clean(row.get("sku_record_id")),
        "source_signature": _row_signature(payload),
        "deterministic_family_id": deterministic_family_id,
        "status": status,
        "best_family_id": parsed.get("best_family_id"),
        "confidence": confidence,
        "code_alignment": parsed.get("code_alignment", "none"),
        "literature_alignment": parsed.get("literature_alignment", "partial"),
        "reasons": parsed.get("reasons") or [],
        "conflicts": parsed.get("conflicts") or [],
        "follow_up_questions": parsed.get("follow_up_questions") or [],
        "canonical_checks": parsed.get("canonical_checks") or {},
    }
    return result


def _family_signature(rows: list[dict]) -> str:
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return digest


def _family_payload(rows: list[pd.Series], families: dict[str, dict]) -> tuple[str, dict, dict, list[dict]]:
    row_payloads = [_row_payload(row) for row in rows]
    deterministic_ids = []
    for row, payload in zip(rows, row_payloads):
        manufacturer = payload["manufacturer"]
        if manufacturer:
            try:
                deterministic_ids.append(get_family_id_for_product(row, manufacturer, families))
            except Exception:
                pass
    family_counter = Counter(deterministic_ids)
    current_family_id = family_counter.most_common(1)[0][0] if family_counter else (row_payloads[0]["source_family_id"] if row_payloads else "")
    aggregated = {
        "manufacturer": ", ".join(sorted({payload["manufacturer"] for payload in row_payloads if payload["manufacturer"]})),
        "our_sku": ", ".join(sorted({payload["our_sku"] for payload in row_payloads if payload["our_sku"]})),
        "supplier_sku": ", ".join(sorted({payload["supplier_sku"] for payload in row_payloads if payload["supplier_sku"]})),
        "product_name": "; ".join(sorted({payload["product_name"] for payload in row_payloads if payload["product_name"]})),
        "category": "; ".join(sorted({payload["category"] for payload in row_payloads if payload["category"]})),
        "material_type": "; ".join(sorted({payload["material_type"] for payload in row_payloads if payload["material_type"]})),
        "product_use": "; ".join(sorted({payload["product_use"] for payload in row_payloads if payload["product_use"]})),
        "mpn": "; ".join(sorted({payload["mpn"] for payload in row_payloads if payload["mpn"]})),
        "validation_status": "; ".join(sorted({payload["validation_status"] for payload in row_payloads if payload["validation_status"]})),
        "validation_notes": "; ".join(sorted({payload["validation_notes"] for payload in row_payloads if payload["validation_notes"]})),
        "bot_content_status": "; ".join(sorted({payload["bot_content_status"] for payload in row_payloads if payload["bot_content_status"]})),
        "source_family_id": current_family_id,
    }
    row_summaries = []
    for row, payload in zip(rows, row_payloads):
        row_summaries.append({
            **payload,
            "sku_record_id": _clean(row.get("sku_record_id")) or payload["our_sku"] or payload["supplier_sku"],
            "row_index": int(row.name) + 2 if getattr(row, "name", None) is not None else None,
            "deterministic_family_id": "",
        })
    return current_family_id, aggregated, row_summaries[0] if row_summaries else {}, row_summaries


def _audit_family(root: Path, family_id: str, rows: list[pd.Series], families: dict[str, dict], model: str, timeout: float) -> dict:
    current_family_id, aggregated, first_row, row_summaries = _family_payload(rows, families)
    candidate_families = _candidate_families(root, families, aggregated)
    candidate_ids = [item["family_id"] for item in candidate_families]
    if current_family_id and current_family_id not in candidate_ids and current_family_id in families:
        candidate_families.append({
            "family_id": current_family_id,
            "score": 10_000,
            "summary": _family_summary(root, families[current_family_id]),
        })
        candidate_ids = [item["family_id"] for item in candidate_families]
    literature = {item["family_id"]: item["summary"] for item in candidate_families}
    prompt = """PRODUCT SHEET FAMILY PACKAGE:
{family_json}

CURRENT FAMILY HINT:
{hint_json}

TOP CANDIDATE FAMILIES:
{candidates_json}

FAMILY LITERATURE EXCERPT:
{literature_json}

Task:
- Decide whether this family mapping is supported by the product sheet rows and literature.
- Use the combined row evidence: manufacturer, product family, material, product use and product code/MPN clues.
- Return the strongest family-level assessment you can.
""".format(
        family_json=json.dumps({
            "family_id": family_id,
            "current_family_id": current_family_id,
            "rows": row_summaries,
            "aggregated": aggregated,
        }, ensure_ascii=False, indent=2),
        hint_json=json.dumps({
            "current_family_id": current_family_id,
            "candidate_ids": candidate_ids,
            "row_count": len(row_summaries),
        }, ensure_ascii=False, indent=2),
        candidates_json=json.dumps(candidate_families, ensure_ascii=False, indent=2),
        literature_json=json.dumps(literature, ensure_ascii=False, indent=2),
    )
    raw = _model_chat(model, SYSTEM_PROMPT, prompt, timeout)
    record = {
        "family_id": family_id,
        "source_family_id": current_family_id,
        "sku_record_id": family_id,
        "source_signature": _family_signature(row_summaries),
        "row_count": len(row_summaries),
        "rows": row_summaries,
        "manufacturer": aggregated["manufacturer"],
        "product_name": aggregated["product_name"],
        "category": aggregated["category"],
        "material_type": aggregated["material_type"],
        "product_use": aggregated["product_use"],
        "mpn": aggregated["mpn"],
        "our_sku": aggregated["our_sku"],
        "supplier_sku": aggregated["supplier_sku"],
        "validation_status": aggregated["validation_status"],
        "validation_notes": aggregated["validation_notes"],
        "bot_content_status": aggregated["bot_content_status"],
    }
    if not raw:
        return {
            **record,
            "status": "model_failed",
            "best_family_id": None,
            "confidence": None,
            "code_alignment": "none",
            "literature_alignment": "partial",
            "reasons": ["Local model unavailable or timed out."],
            "conflicts": [],
            "follow_up_questions": [],
            "canonical_checks": {},
        }
    parsed = _parse_json_reply(raw)
    if parsed is None:
        return {
            **record,
            "status": "model_reply_unparseable",
            "best_family_id": None,
            "confidence": None,
            "code_alignment": "none",
            "literature_alignment": "partial",
            "reasons": ["Local model reply could not be parsed as JSON."],
            "conflicts": [],
            "follow_up_questions": [],
            "canonical_checks": {},
        }
    confidence = parsed.get("confidence")
    if isinstance(confidence, str) and confidence.isdigit():
        confidence = int(confidence)
    elif not isinstance(confidence, int):
        confidence = None
    return {
        **record,
        "status": parsed.get("status") or "needs_more_info",
        "best_family_id": parsed.get("best_family_id") or current_family_id,
        "confidence": confidence,
        "code_alignment": parsed.get("code_alignment", "none"),
        "literature_alignment": parsed.get("literature_alignment", "partial"),
        "reasons": parsed.get("reasons") or [],
        "conflicts": parsed.get("conflicts") or [],
        "follow_up_questions": parsed.get("follow_up_questions") or [],
        "canonical_checks": parsed.get("canonical_checks") or {},
    }


def _load_existing(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {row["sku_record_id"]: row for row in data if isinstance(row, dict) and row.get("sku_record_id")}


def _load_state(path: Path = STATE_JSON) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _family_summary_from_record(family: dict, families: dict[str, dict]) -> dict:
    family_id = family["family_id"]
    canonical = families.get(family_id, {})
    rows = family.get("rows") or []
    confidence = family.get("confidence")
    score = confidence if isinstance(confidence, int) and not isinstance(confidence, bool) else 0
    status = family.get("status") or "needs_more_info"
    review_mode = (
        "quick_glance" if status == "supported" and score >= 85
        else "standard_review" if status in {"supported", "ambiguous", "needs_more_info"} and score >= 70
        else "deep_review"
    )
    return {
        "family_id": family_id,
        "name": canonical.get("name") or family.get("name") or family_id,
        "manufacturer": canonical.get("manufacturer") or family.get("manufacturer", ""),
        "category": canonical.get("category") or family.get("category", ""),
        "knowledge_file": canonical.get("knowledge_file", ""),
        "score": score,
        "status": status,
        "code_alignment": family.get("code_alignment", "none"),
        "literature_alignment": family.get("literature_alignment", "partial"),
        "review_mode": review_mode,
        "row_count": len(rows),
        "quick_glance_rows": len(rows) if review_mode == "quick_glance" else 0,
        "best_family_id": family.get("best_family_id") or "",
        "source_family_id": family.get("source_family_id") or "",
    }


def _family_report(records: dict[str, dict], families: dict[str, dict]) -> str:
    sections = []
    for family in sorted(records.values(), key=lambda record: (
        0 if record.get("status") == "supported" else 1,
        record.get("manufacturer", ""),
        families.get(record.get("family_id", ""), {}).get("name", record.get("family_id", "")),
        record.get("family_id", ""),
    )):
        rows = sorted(family.get("rows") or [], key=lambda row: (
            row.get("our_sku", ""),
            row.get("supplier_sku", ""),
            row.get("sku_record_id", ""),
        ))
        summary = _family_summary_from_record(family, families)
        markdown = lambda value: str(value or "").replace("|", "\\|").replace("\r", " ").replace("\n", " ")
        sections.append(
            "\n".join([
                f"## {summary['manufacturer']} / {summary['family_id']} / {summary['name']}",
                "",
                f"- **Family assessment:** {summary['status']} ({summary['score']}/100 confidence)",
                f"- **Review mode:** {summary['review_mode'].replace('_', ' ')}",
                f"- **SKU rows assessed together:** {summary['row_count']}",
                f"- **Code alignment:** {summary['code_alignment']} | **Literature alignment:** {summary['literature_alignment']}",
                f"- **Quick-glance eligible SKU rows:** {summary['quick_glance_rows']} (family-level assessment; not individual row verification)",
                f"- **Knowledge file:** `{summary['knowledge_file'] or 'n/a'}`",
                f"- **Suggested family:** `{summary['best_family_id'] or 'not determined'}` | **Source family:** `{summary['source_family_id'] or 'not recorded'}`",
                "",
                "| Internal SKU | Supplier code | MPN / product code | Product | Category | Material | Product use |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ] + [
                "| {our_sku} | {supplier_sku} | {mpn} | {product} | {category} | {material} | {use} |".format(
                    our_sku=markdown(row.get("our_sku") or row.get("sku_record_id")),
                    supplier_sku=markdown(row.get("supplier_sku")),
                    mpn=markdown(row.get("mpn")),
                    product=markdown(row.get("product_name")),
                    category=markdown(row.get("category")),
                    material=markdown(row.get("material_type")),
                    use=markdown(row.get("product_use")),
                )
                for row in rows
            ] + [
                "",
                "**Reasons:** " + ("; ".join(markdown(item) for item in family.get("reasons") or []) or "None"),
                "**Conflicts:** " + ("; ".join(markdown(item) for item in family.get("conflicts") or []) or "None"),
                "**Follow-up questions:** " + ("; ".join(markdown(item) for item in family.get("follow_up_questions") or []) or "None"),
                "",
            ])
        )
    return "# Product Sheet Family Review\n\n" + "\n".join(sections)


def _write_reports(records: dict[str, dict], families: dict[str, dict], state: dict) -> None:
    rows = [records[key] for key in sorted(records)]
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    fieldnames = [
        "family_id", "manufacturer", "name", "row_count", "status", "confidence", "code_alignment",
        "literature_alignment", "reasons", "conflicts", "follow_up_questions", "best_family_id",
        "source_family_id", "validation_status", "validation_notes", "bot_content_status",
    ]
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = {
                "family_id": row.get("family_id", ""),
                "manufacturer": row.get("manufacturer", ""),
                "name": families.get(row.get("family_id", ""), {}).get("name", row.get("family_id", "")),
                "row_count": row.get("row_count", 0),
                "status": row.get("status", ""),
                "confidence": row.get("confidence"),
                "code_alignment": row.get("code_alignment", ""),
                "literature_alignment": row.get("literature_alignment", ""),
                "reasons": "; ".join(row.get("reasons") or []),
                "conflicts": "; ".join(row.get("conflicts") or []),
                "follow_up_questions": "; ".join(row.get("follow_up_questions") or []),
                "best_family_id": row.get("best_family_id", ""),
                "source_family_id": row.get("source_family_id", ""),
                "validation_status": row.get("validation_status", ""),
                "validation_notes": row.get("validation_notes", ""),
                "bot_content_status": row.get("bot_content_status", ""),
            }
            writer.writerow(flat)
    OUTPUT_MD.write_text(_family_report(records, families), encoding="utf-8")
    state.update({
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "completed_families": len(records),
        "completed_rows": sum(row.get("row_count", 0) for row in rows),
        "family_count": len(records),
        "supported_families": sum(row.get("status") == "supported" for row in rows),
        "ambiguous_families": sum(row.get("status") == "ambiguous" for row in rows),
        "mismatch_families": sum(row.get("status") == "mismatch" for row in rows),
        "needs_more_info_families": sum(row.get("status") == "needs_more_info" for row in rows),
        "model_failed_families": sum(row.get("status") in {"model_failed", "model_reply_unparseable"} for row in rows),
        "output": {
            "json": OUTPUT_JSON.as_posix(),
            "csv": OUTPUT_CSV.as_posix(),
            "markdown": OUTPUT_MD.as_posix(),
        },
    })
    STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    STATE_JSON.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--sheet", default=DEFAULT_SHEET)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--manufacturer", help="optional exact manufacturer filter")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true", help="skip rows already present in the report")
    parser.add_argument("--retry-failed", action="store_true",
                        help="with --resume, still re-run rows that previously failed or were unparseable")
    parser.set_defaults(family_report=True)
    parser.add_argument("--no-family-report", action="store_false", dest="family_report",
                        help="skip writing the combined family review markdown")
    args = parser.parse_args()

    if not ollama_available():
        print(f"Local Ollama not reachable. Start it with `ollama serve`, ensure `{args.model}` is pulled.", file=sys.stderr)
        raise SystemExit(1)
    if not args.source.exists():
        raise SystemExit(f"BLOCKED: source workbook not found: {args.source}")

    rows, resolved_sheet = _load_rows(args.source, args.sheet)
    families = load_families()
    if args.manufacturer:
        rows = rows[rows["Manufacturer Name"].astype(str).str.casefold() == args.manufacturer.casefold()].copy()
    if rows.empty:
        raise SystemExit("BLOCKED: no rows matched the requested source/manufacturer filters")

    state = _load_state()
    source_hash = _source_hash(args.source)
    state.update({
        "schema_version": STATE_SCHEMA_VERSION,
        "source_path": args.source.as_posix(),
        "source_hash": source_hash,
        "sheet": args.sheet or "auto",
        "resolved_sheet": resolved_sheet or "",
        "model": args.model,
        "manufacturer_filter": args.manufacturer or "",
        "family_report": args.family_report,
    })
    records = _load_existing(OUTPUT_JSON)
    if state.get("schema_version") != STATE_SCHEMA_VERSION:
        records = {}
    if records and not all(isinstance(row, dict) and "family_id" in row and "rows" in row for row in records.values()):
        records = {}
    if state.get("source_hash") and state.get("source_hash") != source_hash:
        records = {}
    if state.get("resolved_sheet") and state.get("resolved_sheet") != (resolved_sheet or ""):
        records = {}
    retryable = {"model_failed", "model_reply_unparseable"}
    grouped: dict[str, list[pd.Series]] = {}
    for _, row in rows.iterrows():
        manufacturer = _clean(row.get("Manufacturer Name"))
        deterministic_family_id = ""
        if manufacturer:
            try:
                deterministic_family_id = get_family_id_for_product(row, manufacturer, families)
            except Exception:
                deterministic_family_id = ""
        source_family_id = _clean(row.get("family_id")) or _clean(row.get("Spec Family Name")) or ""
        group_id = deterministic_family_id if deterministic_family_id and deterministic_family_id != "UNMAPPED" else source_family_id or f"UNMAPPED::{manufacturer or 'unknown'}"
        grouped.setdefault(group_id, []).append(row)

    done = 0
    for family_id in sorted(grouped, key=lambda key: (key.startswith("UNMAPPED::"), key.casefold())):
        family_rows = grouped[family_id]
        preview_rows = [_row_payload(row) for row in family_rows]
        family_signature = _family_signature([
            {**payload, "row_index": int(row.name) + 2 if getattr(row, "name", None) is not None else None}
            for row, payload in zip(family_rows, preview_rows)
        ])
        if args.resume and family_id in records:
            prior = records[family_id]
            same_signature = prior.get("source_signature") == family_signature
            if same_signature and not (args.retry_failed and prior.get("status") in retryable):
                continue
        started = time.time()
        result = _audit_family(ROOT, family_id, family_rows, families, args.model, args.timeout)
        result["source_signature"] = family_signature
        records[family_id] = result
        done += 1
        elapsed = time.time() - started
        print(f"[{done}] {family_id:<32} {result['status']:<18} "
              f"confidence={result.get('confidence')} rows={result.get('row_count')} ({elapsed:.0f}s)", flush=True)
        _write_reports(records, families, state)
        if args.limit and done >= args.limit:
            break

    _write_reports(records, families, state)
    families_out = list(records.values())
    counts = Counter(row.get("status", "unknown") for row in families_out)
    supported = counts.get("supported", 0)
    mismatched = counts.get("mismatch", 0)
    ambiguous = counts.get("ambiguous", 0)
    needs_info = counts.get("needs_more_info", 0)
    print(
        f"\nvalidated: {len(families_out)} families | supported: {supported} | "
        f"ambiguous: {ambiguous} | mismatch: {mismatched} | needs_more_info: {needs_info}"
    )
    print(f"rows covered: {sum(row.get('row_count', 0) for row in families_out)}")
    print(f"wrote {OUTPUT_CSV}, {OUTPUT_JSON}, {OUTPUT_MD} and {STATE_JSON}")


if __name__ == "__main__":
    main()
