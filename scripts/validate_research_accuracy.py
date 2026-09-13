"""Validate research/<family>.json extractions against their source datasheet
using a local Ollama model, producing a per-family accuracy score.

This closes the loop on scripts/tds_research_agent.py: that script asks a
local model (phi4-mini by default) to *extract* structured data from a TDS;
this script asks a second local model (llama3.1:8b by default, deliberately
different from the extractor to avoid the same blind spots) to *check* that
extraction against the original text and flag anything unsupported or missed.

Fully local: reads the archived PDF/DOCX in data/tds/ (or the JSON's stored
excerpt as a fallback), calls only http://127.0.0.1:11434, writes results to
reports/tds_accuracy.csv and reports/tds_accuracy.json. No network egress.

Usage:
    python scripts/validate_research_accuracy.py                  # all "ok" families
    python scripts/validate_research_accuracy.py --only Fletcher
    python scripts/validate_research_accuracy.py --limit 10        # quick pilot run
    python scripts/validate_research_accuracy.py --family FLETCHER_PINK_BATTS_CEILING
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm_client
import tds_research_agent as tra

VALIDATE_MODEL = os.getenv("OLLAMA_VALIDATE_MODEL", "llama3.1:8b")

SYSTEM_PROMPT = (
    "You are a meticulous technical auditor checking whether a structured JSON "
    "spec was extracted correctly from an insulation product's technical data "
    "sheet. You only judge whether claims in the JSON are actually supported by "
    "the source text — you do not judge writing quality or completeness beyond "
    "what is asked."
)

USER_PROMPT_TEMPLATE = """SOURCE TEXT (technical data sheet, may be truncated):
---
{source}
---

EXTRACTED JSON SPEC to audit:
---
{spec}
---

Check the extracted spec against the source text. Return ONLY a JSON object (no markdown fences) with:
  "accuracy_score": integer 0-100. 100 = every technical value (R-values, thickness, dimensions, standards, fire rating, temperatures) in the spec is verifiably present in the source text and nothing is invented. Deduct heavily for any invented/hallucinated number or standard not in the source.
  "unsupported_claims": list of short strings naming any spec value NOT found in the source text (empty list if none).
  "missed_facts": list of up to 5 short strings naming clearly-stated source facts (R-value, standard, dimension) that the spec omitted (empty list if none).
  "range_table_ok": true/false/null — true if a range/variant table is present in the spec and every row's values are traceable to the source text, false if rows look wrong or invented, null if there is no range table to check.
  "notes": one short sentence summary.

Be strict: only mark a value supported if it (or a clear paraphrase with the same number/unit) appears in the source text.
"""


def _text_for_family(data: dict) -> tuple[str, str]:
    """Return (text, text_source) using the archived datasheet if present,
    else the stored excerpt as a lower-confidence fallback."""
    local_path = data.get("datasheet_local_path")
    if local_path:
        full_path = ROOT / local_path
        if full_path.exists():
            text = tra.pdf_text(full_path, max_pages=12)
            if len(text) >= 200:
                return text, "archived_datasheet"
    excerpt = data.get("source_excerpt") or ""
    return excerpt, "stored_excerpt_2000chars"


def _ollama_chat(model: str, system_prompt: str, user_prompt: str, timeout: float) -> str | None:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "think": False,
        "keep_alive": "20m",
        "options": {"temperature": 0, "num_predict": 700, "num_ctx": 8192},
    }
    request = urllib.request.Request(
        f"{llm_client.OLLAMA_HOST}/api/chat",
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


def validate_family(research_path: Path, model: str, timeout: float) -> dict:
    data = json.loads(research_path.read_text(encoding="utf-8"))
    family_id = data["family_id"]
    spec = data.get("spec")
    if data.get("status") != "ok" or not spec:
        return {"family_id": family_id, "status": "skipped_not_ok", "accuracy_score": None}

    text, text_source = _text_for_family(data)
    if len(text) < 200:
        return {"family_id": family_id, "status": "skipped_no_source_text", "accuracy_score": None}

    prompt = USER_PROMPT_TEMPLATE.format(
        source=text[:12000],
        spec=json.dumps(spec, ensure_ascii=False, indent=2)[:6000],
    )
    raw = _ollama_chat(model, SYSTEM_PROMPT, prompt, timeout)
    if not raw:
        return {"family_id": family_id, "status": "validator_call_failed", "accuracy_score": None}
    parsed = _parse_json_reply(raw)
    if parsed is None:
        return {"family_id": family_id, "status": "validator_reply_unparseable", "accuracy_score": None}

    return {
        "family_id": family_id,
        "family_name": data.get("family_name"),
        "manufacturer": research_path.parent.parent.name,
        "status": "validated",
        "text_source": text_source,
        "accuracy_score": parsed.get("accuracy_score"),
        "unsupported_claims": "; ".join(parsed.get("unsupported_claims") or []),
        "missed_facts": "; ".join(parsed.get("missed_facts") or []),
        "range_table_ok": parsed.get("range_table_ok"),
        "notes": parsed.get("notes"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="one manufacturer directory name")
    parser.add_argument("--family", help="one family_id")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--model", default=VALIDATE_MODEL)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    if not llm_client.ollama_available():
        print(f"Local Ollama not reachable. Start it with `ollama serve`, ensure `{args.model}` is pulled.", file=sys.stderr)
        raise SystemExit(1)

    results = []
    done = 0
    for research_path in sorted(ROOT.glob("knowledge/*/research/*.json")):
        manufacturer_dir = research_path.parent.parent.name
        if args.only and manufacturer_dir.casefold() != args.only.casefold():
            continue
        if args.family:
            data = json.loads(research_path.read_text(encoding="utf-8"))
            if data.get("family_id") != args.family:
                continue
        if args.limit and done >= args.limit:
            break
        result = validate_family(research_path, args.model, args.timeout)
        results.append(result)
        done += 1
        score = result.get("accuracy_score")
        print(f"[{done}] {result['family_id']:<40} {result['status']:<24} score={score}")

    out_json = ROOT / "reports" / "tds_accuracy.json"
    out_csv = ROOT / "reports" / "tds_accuracy.csv"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    fieldnames = ["family_id", "family_name", "manufacturer", "status", "text_source",
                  "accuracy_score", "unsupported_claims", "missed_facts", "range_table_ok", "notes"]
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    validated = [r for r in results if r.get("accuracy_score") is not None]
    if validated:
        avg = sum(r["accuracy_score"] for r in validated) / len(validated)
        low = [r for r in validated if r["accuracy_score"] < 80]
        print(f"\nvalidated: {len(validated)}/{len(results)}  avg accuracy: {avg:.1f}")
        print(f"below 80: {len(low)}")
        for r in sorted(low, key=lambda x: x["accuracy_score"])[:15]:
            print(f"  {r['accuracy_score']:>3}  {r['family_id']:<40} {r['notes']}")
    print(f"\nwrote {out_csv} and {out_json}")


if __name__ == "__main__":
    main()
