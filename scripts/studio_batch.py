"""Batch helper for running the deep-dive research in Google AI Studio.

AI Studio's chat can't run unattended, so this splits the work into batches you
paste in manually (or run a few chats in parallel). It produces one prompt per
batch that returns a JSON ARRAY of per-family results, and an ingester that
validates and writes each result into knowledge/<mfg>/research/<slug>.json so
the literature generator picks it up.

Workflow:
  1. python scripts/studio_batch.py make --batch 1 --size 10
       -> writes output/studio_batches/batch_001_prompt.txt
  2. In AI Studio (aistudio.google.com), new chat, model Gemini 2.5 Pro,
     Google Search ON, paste the prompt. It returns a JSON array.
  3. Save that array to output/studio_batches/batch_001_result.json
  4. python scripts/studio_batch.py ingest --batch 1
       -> validates + writes each family, regenerates its literature
  5. Repeat for batches 2, 3, ...

  python scripts/studio_batch.py status     # how many families are researched
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import tds_research_agent as agent
from research_next_family import TERMINAL_STATUSES  # families already done/terminal

BATCH_DIR = ROOT / "output" / "studio_batches"

BATCH_PROMPT = """You are researching {n} insulation product families for an Australian supplier's knowledge base. For EACH family, use Google Search to find the OFFICIAL manufacturer Technical Data Sheet (TDS) and Safety Data Sheet (SDS) on the manufacturer's own website, read them, and extract the data.

Return ONLY a single JSON array (no markdown fences, no commentary). The array must have exactly {n} objects, one per family IN THE SAME ORDER AS LISTED BELOW. Each object must have:

  "family_id": the exact family_id string from the list below (copy it verbatim),
  "tds_url": absolute URL of the official TDS (PDF or product page), or "" if not found,
  "sds_url": absolute URL of the official SDS, or "" if not found,
  "description": 2-4 sentence factual description from the TDS,
  "features": up to 10 short feature strings the manufacturer actually states,
  "applications": list of applications (e.g. "ceiling", "external wall", "pipe"),
  "technical": list of {{"property","value","standard"}} objects for every spec found (R-values per thickness, density, thickness, dimensions, thermal conductivity, temperature range, vapour, acoustic Rw/NRC, fire indices). Use "" for standard if none stated,
  "range": list of {{"variant","size_or_rating","pack"}} objects for available variants/sizes/grades,
  "fire": string of fire test results (AS/NZS 1530.3 indices, AS 1530.1, BAL), or "",
  "compliance": string of NCC/standard compliance claims exactly as stated, or "",
  "sustainability": string of recycled-content / VOC / environmental claims, or "",
  "install": up to 10 short installation steps from the TDS,
  "selection_checklist": up to 8 short things a buyer must confirm before selecting,
  "accessories": list of companion products/tapes/adhesives specified, or [],
  "limitations": up to 8 manufacturer-stated limitations or warnings, or [],
  "warranty": short string of the stated warranty term, or "",
  "found": true if you located a real manufacturer TDS, false otherwise.

Rules: report ONLY what manufacturer documents actually state. Never invent numbers, URLs, test results or claims. Keep numbers and units exactly as written. Prefer the manufacturer's own site over resellers. If you cannot find a TDS for a family, still include its object with "found": false and empty fields.

FAMILIES (in order):
{family_list}

Return the JSON array now.
"""


def all_families() -> list[tuple[str, dict]]:
    items = []
    for path in sorted(ROOT.glob("knowledge/*/families.json")):
        mdir = path.parent.name
        data = json.loads(path.read_text(encoding="utf-8"))
        for family in data["families"]:
            family.setdefault("manufacturer", mdir.title())
            items.append((mdir, family))
    return items


def pending_families() -> list[tuple[str, dict]]:
    pending = []
    for mdir, family in all_families():
        slug = agent.slugify(family["name"])
        rf = agent.research_path(mdir, slug)
        status = None
        if rf.exists():
            try:
                status = json.loads(rf.read_text(encoding="utf-8")).get("status")
            except (json.JSONDecodeError, OSError):
                status = None
        if status != "ok":
            pending.append((mdir, family))
    return pending


def make_batch(batch_no: int, size: int) -> Path:
    pending = pending_families()
    start = (batch_no - 1) * size
    chunk = pending[start:start + size]
    if not chunk:
        print(f"no pending families for batch {batch_no} (pending total: {len(pending)})")
        sys.exit(1)
    family_list = "\n".join(
        f"{i+1}. family_id={f['family_id']} | manufacturer={mdir} | family={f['name']} | category={f.get('category','')}"
        for i, (mdir, f) in enumerate(chunk)
    )
    prompt = BATCH_PROMPT.format(n=len(chunk), family_list=family_list)
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    out = BATCH_DIR / f"batch_{batch_no:03d}_prompt.txt"
    out.write_text(prompt, encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}  ({len(chunk)} families)")
    print(f"paste this into AI Studio, then save the JSON array reply to {BATCH_DIR.relative_to(ROOT)}/batch_{batch_no:03d}_result.json")
    return out


def _result_path(batch_no: int) -> Path:
    return BATCH_DIR / f"batch_{batch_no:03d}_result.json"


def ingest_batch(batch_no: int) -> None:
    path = _result_path(batch_no)
    if not path.exists():
        print(f"missing {path.relative_to(ROOT)} - save the AI Studio JSON array there first")
        sys.exit(1)
    raw = path.read_text(encoding="utf-8-sig")
    match = re.search(r"\[.*\]", raw, re.S)
    if not match:
        print("no JSON array found in the result file")
        sys.exit(1)
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        print(f"invalid JSON: {exc}")
        sys.exit(1)

    by_id = {f["family_id"]: (mdir, f) for mdir, f in all_families()}
    written = failed = 0
    touched_dirs = set()
    for item in items:
        fid = item.get("family_id")
        if fid not in by_id:
            print(f"  skip unknown family_id: {fid}")
            failed += 1
            continue
        mdir, family = by_id[fid]
        found = bool(item.get("found")) and bool(item.get("description") or item.get("technical"))
        spec = {k: item.get(k) for k in ("description","features","applications","technical","range","fire","compliance","sustainability","install","selection_checklist","accessories","limitations","warranty")}
        out_path = agent.research_path(mdir, agent.slugify(family["name"]))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({
            "family_id": fid, "family_name": family["name"],
            "datasheet_pdf_url": item.get("tds_url", ""), "sds_url": item.get("sds_url", ""),
            "status": "ok" if found else "gemini_not_found",
            "researched_at": __import__("time").strftime("%Y-%m-%d"),
            "spec": spec, "source_excerpt": None, "engine": "ai_studio_batch",
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        touched_dirs.add(mdir)
        written += 1
        print(f"  {'ok' if found else 'NOT FOUND'}  {family['name'][:50]}")

    print(f"\nwritten: {written}, skipped: {failed}")
    # regenerate literature for touched manufacturers
    for mdir in sorted(touched_dirs):
        subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_family_literature.py"), "--only", mdir], cwd=ROOT, capture_output=True)
    print("literature regenerated for:", ", ".join(sorted(touched_dirs)))


def status() -> None:
    total = len(all_families())
    done = total - len(pending_families())
    print(f"researched: {done} / {total}  (pending: {len(pending_families())})")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make"); m.add_argument("--batch", type=int, required=True); m.add_argument("--size", type=int, default=10)
    i = sub.add_parser("ingest"); i.add_argument("--batch", type=int, required=True)
    sub.add_parser("status")
    args = parser.parse_args()

    if args.cmd == "make":
        make_batch(args.batch, args.size)
    elif args.cmd == "ingest":
        ingest_batch(args.batch)
    else:
        status()


if __name__ == "__main__":
    main()
