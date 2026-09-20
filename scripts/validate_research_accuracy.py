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
    python scripts/validate_research_accuracy.py --resume          # continue a long sweep
    python scripts/validate_research_accuracy.py --resume --retry-failed

Results are merged into the existing report and flushed after every family, so
a filtered run never discards untouched families and an interrupted multi-hour
sweep can be resumed with --resume.

Environment:
    OLLAMA_VALIDATE_MODEL    auditing model (default llama3.1:8b)
    OLLAMA_VALIDATE_TIMEOUT  per-family seconds (default 900; ~265s is typical
                             on a CPU-only box, so do not lower this casually)
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

# Auditing one family costs ~265s on a CPU-only box with llama3.1:8b. The old
# 120s default silently turned nearly every family into "validator_call_failed",
# which read like a model problem but was pure timeout.
VALIDATE_TIMEOUT = float(os.getenv("OLLAMA_VALIDATE_TIMEOUT", "900"))

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
        # No archived datasheet and no usable excerpt: the spec exists but no
        # evidence was retained, so it can never be audited. This is a sourcing
        # gap, not a validator failure, and must not be confused with one.
        return {"family_id": family_id, "status": "skipped_no_source_text", "accuracy_score": None}

    prompt = USER_PROMPT_TEMPLATE.format(
        source=text[:12000],
        spec=json.dumps(spec, ensure_ascii=False, indent=2)[:6000],
    )

    raw = None
    for attempt in range(2):
        raw = _ollama_chat(model, SYSTEM_PROMPT, prompt, timeout)
        if raw:
            break
        if attempt == 0:
            print("    retrying once after validator call failure", file=sys.stderr)
            time.sleep(5)
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


FIELDNAMES = ["family_id", "family_name", "manufacturer", "status", "text_source",
              "accuracy_score", "unsupported_claims", "missed_facts", "range_table_ok", "notes"]


def _load_existing(out_json: Path) -> dict[str, dict]:
    if not out_json.exists():
        return {}
    try:
        return {r["family_id"]: r for r in json.loads(out_json.read_text(encoding="utf-8"))}
    except (json.JSONDecodeError, KeyError, TypeError):
        print(f"warning: could not read {out_json}, starting fresh", file=sys.stderr)
        return {}


def _write_reports(records: dict[str, dict], out_json: Path, out_csv: Path) -> None:
    rows = [records[k] for k in sorted(records)]
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="one manufacturer directory name")
    parser.add_argument("--family", help="one family_id")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--model", default=VALIDATE_MODEL)
    parser.add_argument("--timeout", type=float, default=VALIDATE_TIMEOUT)
    parser.add_argument("--resume", action="store_true",
                        help="skip families already validated in the existing report")
    parser.add_argument("--retry-failed", action="store_true",
                        help="with --resume, still re-run families that previously errored")
    args = parser.parse_args()

    if not llm_client.ollama_available():
        print(f"Local Ollama not reachable. Start it with `ollama serve`, ensure `{args.model}` is pulled.", file=sys.stderr)
        raise SystemExit(1)

    out_json = ROOT / "reports" / "tds_accuracy.json"
    out_csv = ROOT / "reports" / "tds_accuracy.csv"

    # Merge into any previous report. A filtered run (--family/--only/--limit)
    # must never discard the families it did not look at.
    records = _load_existing(out_json)

    retryable = {"validator_call_failed", "validator_reply_unparseable"}
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

        if args.resume:
            prior = records.get(json.loads(research_path.read_text(encoding="utf-8"))["family_id"])
            if prior is not None:
                stale = args.retry_failed and prior.get("status") in retryable
                if not stale:
                    continue

        started = time.time()
        result = validate_family(research_path, args.model, args.timeout)
        records[result["family_id"]] = result
        done += 1
        score = result.get("accuracy_score")
        elapsed = time.time() - started
        print(f"[{done}] {result['family_id']:<40} {result['status']:<24} "
              f"score={score} ({elapsed:.0f}s)", flush=True)

        # Persist after every family: a multi-hour CPU sweep must survive an
        # interrupt without losing completed work.
        _write_reports(records, out_json, out_csv)

    _write_reports(records, out_json, out_csv)

    rows = list(records.values())
    validated = [r for r in rows if r.get("accuracy_score") is not None]
    if validated:
        avg = sum(r["accuracy_score"] for r in validated) / len(validated)
        low = [r for r in validated if r["accuracy_score"] < 80]
        print(f"\nvalidated: {len(validated)}/{len(rows)}  avg accuracy: {avg:.1f}")
        print(f"below 80: {len(low)}")
        for r in sorted(low, key=lambda x: x["accuracy_score"])[:15]:
            print(f"  {r['accuracy_score']:>3}  {r['family_id']:<40} {r['notes']}")
    print(f"\nwrote {out_csv} and {out_json}")


if __name__ == "__main__":
    main()
