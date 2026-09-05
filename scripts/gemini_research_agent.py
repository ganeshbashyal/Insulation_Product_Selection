"""Gemini-powered deep-dive research agent.

Per family, asks Gemini (with Google Search grounding) to find the official
manufacturer TDS/SDS links AND extract the structured product spec directly,
then writes knowledge/<mfg>/research/<slug>.json. The literature generator then
folds the real data into the MD/DOCX.

NOTE: this sends family/manufacturer names and datasheet text to Google's API
(user-approved for the research step). The deterministic ranker, customer data
and the local chat path remain local-only.

Set the key first:
    $env:GEMINI_API_KEY = "your-key"        # PowerShell
    export GEMINI_API_KEY=your-key          # bash

Run one family at a time (resumable, one JSON per family):
    python scripts/gemini_research_agent.py                 # next pending family
    python scripts/gemini_research_agent.py --loop          # until none pending
    python scripts/gemini_research_agent.py --only Fletcher # one manufacturer
    python scripts/gemini_research_agent.py --status        # progress
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_datasheet_links import OFFICIAL_DOMAINS
import tds_research_agent as local_agent  # reuse slugify, research_path, caching helpers

# Pro model for deep-dive quality (billing enabled); override with GEMINI_MODEL.
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
MAX_RETRIES = 5

SPEC_KEYS = [
    "description", "features", "applications", "technical", "range", "fire",
    "sustainability", "install", "selection_checklist", "compliance",
    "warranty", "limitations", "accessories",
]

RESEARCH_PROMPT = """You are doing a deep-dive technical literature review of one insulation product family for an Australian supplier. The output feeds customer-facing sales/SEO pages and Word documents, so be thorough and precise.

Manufacturer: {manufacturer}
Product family: {family}
Category: {category}

Using web search, locate the OFFICIAL manufacturer Technical Data Sheet (TDS) and Safety Data Sheet (SDS) on the manufacturer's own website, read them fully, and return ONLY a JSON object (no markdown fences, no commentary) with these keys:

  "tds_url": absolute URL of the official TDS (PDF or product page), or "" if not found.
  "sds_url": absolute URL of the official SDS, or "" if not found.
  "description": 2-4 sentence factual description of the product, its material and construction, from the TDS.
  "features": up to 12 short feature strings actually stated by the manufacturer.
  "applications": list of applications (e.g. "ceiling", "external wall", "pipe").
  "technical": list of {{"property","value","standard"}} objects for EVERY spec in the TDS: R-values per thickness, density, thickness range, dimensions, thermal conductivity, service/operating temperature, water vapour, moisture absorption, corrosion, acoustic ratings (Rw/NRC/aw), UV/weather, compression, etc. Use "" for standard if none stated. Be exhaustive.
  "range": list of {{"variant","size_or_rating","pack"}} objects describing the available variants/sizes/grades with dimensions or R-values and pack/bag quantities if published.
  "fire": string with fire test results and indices (e.g. AS/NZS 1530.3 ignitability/spread/heat/smoke, AS 1530.1 combustibility, BAL), or "" if none.
  "compliance": string describing NCC/standard compliance claims and certifications exactly as stated (CodeMark, AS/NZS 4859.1, etc.), or "" if none.
  "sustainability": string of recycled-content / VOC / Green Star / EPD / environmental claims, or "" if none.
  "install": up to 12 short installation steps from the TDS.
  "selection_checklist": up to 8 short things a buyer must confirm before selecting (e.g. "measure pipe OD and match insulation ID").
  "accessories": list of companion products/tapes/adhesives the manufacturer specifies, or [] if none.
  "limitations": up to 8 manufacturer-stated limitations, warnings or exclusions, or [] if none.
  "warranty": short string of the stated warranty term, or "" if none.
  "found": true if you located a real manufacturer TDS, false otherwise.

Rules: report ONLY what the manufacturer documents actually state — never invent numbers, URLs, test results or claims. Keep numbers and units exactly as written. If a field is absent use "" or []. Prefer the manufacturer's own site over resellers.
"""


def _client():
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    from google import genai
    return genai.Client(api_key=key)


def research_family(manufacturer: str, family: dict) -> dict:
    """Ask Gemini (search-grounded) to find links + extract the spec."""
    from google.genai import types

    prompt = RESEARCH_PROMPT.format(
        manufacturer=manufacturer,
        family=family["name"],
        category=family.get("category", ""),
    )
    client = _client()
    grounding = types.Tool(google_search=types.GoogleSearch())
    text = ""
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            chat = client.chats.create(
                model=MODEL,
                config=types.GenerateContentConfig(tools=[grounding], temperature=0),
            )
            response = chat.send_message(prompt)
            text = response.text or ""
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                wait = min(60, 10 * (2 ** attempt))  # 10s,20s,40s,60s,60s
                print(f"  quota hit, waiting {wait}s (attempt {attempt+1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            raise
    else:
        raise RuntimeError(f"Gemini failed after {MAX_RETRIES} attempts: {last_error}")
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {"status": "gemini_no_json", "raw": text[:500]}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"status": "gemini_bad_json", "raw": text[:500]}

    spec = {k: data.get(k) for k in SPEC_KEYS}
    found = bool(data.get("found")) and bool(spec.get("description") or spec.get("technical"))
    return {
        "status": "ok" if found else "gemini_not_found",
        "datasheet_pdf_url": data.get("tds_url", ""),
        "sds_url": data.get("sds_url", ""),
        "spec": spec,
        "source_excerpt": None,
    }


def _write(manufacturer_dir: str, family: dict, result: dict) -> None:
    slug = local_agent.slugify(family["name"])
    out_path = local_agent.research_path(manufacturer_dir, slug)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "family_id": family["family_id"],
        "family_name": family["name"],
        "datasheet_pdf_url": result.get("datasheet_pdf_url", ""),
        "sds_url": result.get("sds_url", ""),
        "status": result.get("status"),
        "researched_at": time.strftime("%Y-%m-%d"),
        "spec": result.get("spec"),
        "source_excerpt": result.get("source_excerpt"),
        "engine": "gemini",
    }, indent=2, ensure_ascii=False), encoding="utf-8")


def pending(manufacturer: str | None = None) -> list[tuple[str, dict]]:
    items = []
    for path in sorted(ROOT.glob("knowledge/*/families.json")):
        mdir = path.parent.name
        if manufacturer and mdir.casefold() != manufacturer.casefold():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for family in data["families"]:
            family.setdefault("manufacturer", mdir.title())
            slug = local_agent.slugify(family["name"])
            rf = local_agent.research_path(mdir, slug)
            status = None
            if rf.exists():
                try:
                    status = json.loads(rf.read_text(encoding="utf-8")).get("status")
                except (json.JSONDecodeError, OSError):
                    status = None
            if status != "ok":
                items.append((mdir, family))
    return items


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--delay", type=float, default=2.0)
    args = parser.parse_args()

    if args.status:
        local_agent.status_report()
        print(f"pending: {len(pending())}")
        return

    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        print("GEMINI_API_KEY is not set. Set it first, e.g.:  $env:GEMINI_API_KEY = \"...\"")
        sys.exit(1)

    queue = pending(args.only)
    print(f"pending families: {len(queue)}")
    processed = 0
    while queue:
        mdir, family = queue.pop(0)
        print(f"[{processed+1}] {mdir} / {family['name'][:55]}")
        try:
            result = research_family(mdir, family)
        except Exception as exc:  # noqa: BLE001 - keep the batch moving
            print(f"  -> error: {exc}")
            result = {"status": "gemini_error", "spec": None}
        _write(mdir, family, result)
        print(f"  -> {result.get('status')}  tds={result.get('datasheet_pdf_url','')[:70]}")
        processed += 1
        if not args.loop:
            break
        time.sleep(args.delay)
        queue = pending(args.only)

    print(f"\nprocessed this run: {processed}")


if __name__ == "__main__":
    main()
