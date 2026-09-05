"""Ingest the hand-supplied "Australian Insulation Knowledge Base" text dumps.

These files carry per-family granular sizing/packaging tables AND bot
decision-making logic (search synonyms, problem triggers, placement, negative
filters, substitutes, upsells). This parser extracts that structure and merges
it into each family's research JSON so the literature pages AND the ranker use
it. It is reusable for future files in the same format.

Usage:
    python scripts/ingest_knowledge_base_txt.py "path\to\file.txt" [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import tds_research_agent as agent


def slugify(name: str) -> str:
    return agent.slugify(name)


def split_families(text: str) -> list[tuple[str, str]]:
    """Split into (family_id, body) chunks at 'N. FAMILY_ID' headers."""
    pattern = re.compile(r"(?m)^\d+\.\s+([A-Z][A-Z0-9_]+)\s*(?:\([^)]*\))?\s*$")
    matches = list(pattern.finditer(text))
    chunks = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunks.append((m.group(1), text[start:end]))
    return chunks


def bullet_list(body: str, label: str) -> list[str]:
    """Extract the bullet list following a '* Label:' marker."""
    pattern = re.compile(rf"{re.escape(label)}[:\s]*(.*?)(?=\n\s*•\s*[A-Z][^\n]*:|\Z)", re.S)
    match = pattern.search(body)
    if not match:
        return []
    segment = match.group(1)
    # strip the leading label remnant and split into quoted terms / sentences
    segment = re.sub(r"^\W*", "", segment)
    parts = re.split(r";|\n", segment)
    out = []
    for part in parts:
        part = part.strip().strip("•").strip()
        part = part.strip('"').strip()
        if part:
            out.append(part)
    return out


def quoted_terms(body: str, label: str) -> list[str]:
    """Extract the quoted search/synonym terms after a label."""
    pattern = re.compile(rf"{re.escape(label)}[:\s]*(.*?)(?=\n\s*•|\Z)", re.S)
    match = pattern.search(body)
    if not match:
        return []
    return [t.strip() for t in re.findall(r'"([^"]+)"', match.group(1)) if t.strip()]


def field_text(body: str, label: str) -> str:
    pattern = re.compile(rf"{re.escape(label)}[:\s]*(.*?)(?=\n\s*•|\n\n|\Z)", re.S)
    match = pattern.search(body)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def parse_placement(body: str) -> list[str]:
    text = field_text(body, "Placement")
    if not text:
        return []
    text = text.rstrip(".")
    return [p.strip() for p in re.split(r",|/", text) if p.strip()]


def parse_size_table(body: str) -> list[dict]:
    """Extract the tab-separated granular sizing matrix rows (best-effort)."""
    section = re.search(r"Granular Sizing & Dimensional Matrix\n(.*?)(?=\nBot Decision-Making|\Z)", body, re.S)
    if not section:
        return []
    rows = []
    for line in section.group(1).splitlines():
        line = line.strip()
        if not line or "\t" not in line:
            continue
        cells = [c.strip() for c in line.split("\t") if c.strip()]
        if len(cells) >= 2:
            rows.append({f"c{i}": cell for i, cell in enumerate(cells)})
    return rows


def find_family(family_id: str) -> tuple[str, dict] | None:
    for path in sorted(ROOT.glob("knowledge/*/families.json")):
        mdir = path.parent.name
        for family in json.loads(path.read_text(encoding="utf-8"))["families"]:
            if family["family_id"] == family_id:
                return mdir, family
    return None


def merge_family(family_id: str, body: str, dry_run: bool) -> str:
    found = find_family(family_id)
    if not found:
        return "no_family"
    mdir, family = found

    retrieval = {
        "search_keywords": quoted_terms(body, "Search Triggers"),
        "problem_keywords": bullet_list(body, "Problem Triggers"),
        "placement": parse_placement(body),
        "not_for": bullet_list(body, "Negative Filter"),
        "use_cases": bullet_list(body, "Positive Recommendation Rule"),
    }
    retrieval = {k: v for k, v in retrieval.items() if v}
    substitute = field_text(body, "Substitute Mapping") or field_text(body, "Substitute")
    upsell = field_text(body, "Accessories Upsell") or field_text(body, "Complementary Upsell")
    range_rows = parse_size_table(body)

    slug = slugify(family["name"])
    path = ROOT / "knowledge" / mdir / "research" / f"{slug}.json"
    if dry_run:
        return f"would update {family_id} (keywords={len(retrieval.get('search_keywords', []))}, range={len(range_rows)})"

    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {
            "family_id": family_id, "family_name": family["name"],
            "datasheet_pdf_url": "", "sds_url": "", "status": "ok",
            "researched_at": time.strftime("%Y-%m-%d"),
            "spec": {}, "retrieval": {}, "source_excerpt": None,
            "engine": "knowledge_base_txt",
        }
    # guard against null spec/retrieval from earlier pipeline stages
    if not isinstance(data.get("spec"), dict):
        data["spec"] = {}
    if not isinstance(data.get("retrieval"), dict):
        data["retrieval"] = {}
    spec = data["spec"]
    existing_retrieval = data["retrieval"]
    for key, values in retrieval.items():
        merged = sorted(set(existing_retrieval.get(key, [])) | set(values))
        existing_retrieval[key] = merged
    if range_rows:
        spec["range"] = range_rows
        data["range_source"] = "manufacturer granular sizing matrix (knowledge-base dump)"
    if substitute:
        spec["substitutes"] = substitute
    if upsell:
        spec["accessories_upsell"] = upsell
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return "ok"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="path to the knowledge-base text dump")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    text = Path(args.file).read_text(encoding="utf-8")
    chunks = split_families(text)
    print(f"families found in file: {len(chunks)}")
    tally: dict[str, int] = {}
    for family_id, body in chunks:
        result = merge_family(family_id, body, args.dry_run)
        tally[result.split()[0]] = tally.get(result.split()[0], 0) + 1
        if result != "ok" or args.dry_run:
            print(f"  {family_id:<52} {result}")
    print("\ntally:", tally)


if __name__ == "__main__":
    main()
