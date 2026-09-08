"""Chunk the raw compliance corpus into retrievable, citable chunks.

knowledge/industry/compliance/raw/ holds ~1.3 MB of extracted ABCB/NCC text
(both NCC volumes, the condensation and sound handbooks, AIIC reports) plus
~220 KB of curated markdown. None of it was reachable by the retriever, so the
bot could not answer from the primary compliance sources at all.

This builds compliance_rag_chunks.jsonl in the same shape the retriever already
loads (topic/module_title/text), preserving the page markers and NCC clause
identifiers so every answer can cite a locatable place in the source.

Local only: plain text processing, no network, no cloud APIs.

    python scripts/build_compliance_chunks.py --summary
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDUSTRY = ROOT / "knowledge" / "industry"
RAW_DIR = INDUSTRY / "compliance" / "raw"
OUT_PATH = INDUSTRY / "training" / "compliance_rag_chunks.jsonl"

TARGET_CHARS = 1600
OVERLAP_CHARS = 200
MIN_CHARS = 220

# Curated prose worth retrieving. READMEs and index pages are navigation, not
# knowledge, so they are deliberately excluded.
MARKDOWN_SOURCES = [
    "compliance/01_condensation_management.md",
    "compliance/02_sound_transmission.md",
    "compliance/03_ncc_energy_efficiency.md",
    "compliance/04_industry_reports.md",
    "compliance/05_standards_reference.md",
    "principles/01_thermal_principles.md",
    "principles/02_acoustic_principles.md",
    "product_intelligence/01_manufacturers_suppliers.md",
    "product_intelligence/02_products_application.md",
    "product_intelligence/03_materials_applications.md",
    "product_intelligence/04_product_rvalue_catalogue.md",
    "customer_support/01_top_50_customer_problems.md",
    "customer_support/02_quick_triage.md",
    "training/01_glossary.md",
    "training/02_climate_zone_guide.md",
    "training/03_installation_guide.md",
    "training/04_bushfire.md",
    "AU_Insulation_Expert_Knowledge_Base.md",
]

RAW_TITLES = {
    "ncc_vol1_commercial": ("NCC Volume One (Commercial)", "NCC Volume One"),
    "ncc_vol2_housing": ("NCC Volume Two (Housing)", "NCC Volume Two"),
    "condensation_handbook": ("ABCB Condensation in Buildings Handbook", "ABCB Handbook"),
    "sound_handbook": ("ABCB Sound Transmission and Insulation Handbook", "ABCB Handbook"),
    "aiic_insulation_2024": ("Insulation in Australia 2024 (AIIC)", "Industry report"),
    "aiic_policy_2024": ("AIIC Policy Position 2024", "Industry report"),
    "aiic_traffic_light_2025": ("AIIC Traffic Light Report 2025", "Industry report"),
}

PAGE_RE = re.compile(r"=====\s*PAGE\s+(\d+)\s*=====")
# NCC clause identifiers, e.g. H4D9, J1D5, 10.8.1, F5P1, Part H2, Spec 13.
CLAUSE_RE = re.compile(
    r"\b(?:[A-J]\d[A-Z]\d{1,2}|Part\s+[A-J]?\d+(?:\.\d+)*|Spec(?:ification)?\s+[\w.]+|\d{1,2}\.\d(?:\.\d+)*)\b"
)


def clean(text: str) -> str:
    """Normalise PDF extraction noise without destroying clause numbering."""
    text = text.replace("\u200a", " ").replace("\xa0", " ")
    # Dotted tables of contents carry no retrievable meaning.
    text = re.sub(r"\.{4,}\s*\d*", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_pages(text: str) -> list[tuple[int, str]]:
    """Split on page markers, keeping each page's number for citation."""
    parts = PAGE_RE.split(text)
    if len(parts) == 1:
        return [(0, text)]
    pages = []
    # parts = [pre, num, body, num, body, ...]
    for i in range(1, len(parts) - 1, 2):
        pages.append((int(parts[i]), parts[i + 1]))
    return pages


def pack(segments: list[tuple[int, str]]) -> list[tuple[str, int, int]]:
    """Greedily pack pages into ~TARGET_CHARS chunks, tracking page span."""
    chunks: list[tuple[str, int, int]] = []
    buf, first, last = "", None, None
    for page, body in segments:
        body = clean(body)
        if not body:
            continue
        if first is None:
            first, last = page, page
        if len(buf) + len(body) + 1 <= TARGET_CHARS or not buf:
            buf = f"{buf}\n{body}".strip() if buf else body
            last = page
            continue
        chunks.append((buf, first, last))
        tail = buf[-OVERLAP_CHARS:] if OVERLAP_CHARS else ""
        buf = f"{tail}\n{body}".strip()
        first, last = page, page
    if buf.strip():
        chunks.append((buf, first or 0, last or 0))
    return [c for c in chunks if len(c[0]) >= MIN_CHARS]


def split_markdown(text: str) -> list[tuple[str, str]]:
    """Split markdown on headings so each chunk keeps its own section title."""
    sections: list[tuple[str, str]] = []
    current, buf = "", []
    for line in text.splitlines():
        if re.match(r"^#{1,3}\s+", line):
            if buf and "\n".join(buf).strip():
                sections.append((current, "\n".join(buf).strip()))
            current = re.sub(r"^#+\s*", "", line).strip()
            buf = []
        else:
            buf.append(line)
    if buf and "\n".join(buf).strip():
        sections.append((current, "\n".join(buf).strip()))

    out: list[tuple[str, str]] = []
    for title, body in sections:
        body = clean(body)
        if len(body) < MIN_CHARS:
            continue
        if len(body) <= TARGET_CHARS:
            out.append((title, body))
            continue
        for i in range(0, len(body), TARGET_CHARS - OVERLAP_CHARS):
            piece = body[i:i + TARGET_CHARS]
            if len(piece) >= MIN_CHARS:
                out.append((title, piece))
    return out


def clauses(text: str) -> list[str]:
    found = []
    for match in CLAUSE_RE.findall(text):
        token = match.strip()
        if token not in found:
            found.append(token)
    return found[:8]


def build() -> list[dict]:
    chunks: list[dict] = []

    for path in sorted(RAW_DIR.glob("*.txt")):
        stem = path.stem
        title, module = RAW_TITLES.get(stem, (stem.replace("_", " ").title(), "Compliance source"))
        raw = path.read_text(encoding="utf-8", errors="replace")
        for text, first, last in pack(split_pages(raw)):
            page = f"p{first}" if first == last else f"pp{first}-{last}"
            found = clauses(text)
            topic = f"{title} ({page})"
            if found:
                topic = f"{title} {found[0]} ({page})"
            chunks.append({
                "chunk_id": hashlib.sha256(
                    f"{stem}|{first}|{text[:120]}".encode()
                ).hexdigest()[:16],
                "topic": topic,
                "module_id": stem,
                "module_title": module,
                "kind": "regulation" if stem.startswith("ncc") else "guidance",
                "source_file": f"knowledge/industry/compliance/raw/{path.name}",
                "page_start": first,
                "page_end": last,
                "clauses": found,
                "text": text,
                "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
            })

    for rel in MARKDOWN_SOURCES:
        path = INDUSTRY / rel
        if not path.exists():
            print(f"  skip (missing): {rel}")
            continue
        doc_title = path.stem.replace("_", " ").strip()
        doc_title = re.sub(r"^\d+\s*", "", doc_title).title()
        body = path.read_text(encoding="utf-8", errors="replace")
        for section, text in split_markdown(body):
            topic = f"{doc_title} - {section}" if section else doc_title
            chunks.append({
                "chunk_id": hashlib.sha256(
                    f"{rel}|{section}|{text[:120]}".encode()
                ).hexdigest()[:16],
                "topic": topic,
                "module_id": path.stem,
                "module_title": "Curated knowledge base",
                "kind": "reference",
                "source_file": f"knowledge/industry/{rel}",
                "clauses": clauses(text),
                "text": text,
                "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
            })

    # Identical text can appear on repeated pages; keep the first occurrence.
    seen: set[str] = set()
    unique = []
    for chunk in chunks:
        if chunk["content_sha256"] in seen:
            continue
        seen.add(chunk["content_sha256"])
        unique.append(chunk)
    return unique


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    if not RAW_DIR.exists():
        raise SystemExit(f"missing raw corpus: {RAW_DIR}")

    chunks = build()
    chunks.sort(key=lambda c: (c["module_id"], c.get("page_start", 0), c["chunk_id"]))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    print(f"wrote {len(chunks)} chunks to {OUT_PATH.relative_to(ROOT)}")

    if args.summary:
        by_module: dict[str, int] = {}
        with_clause = 0
        for chunk in chunks:
            by_module[chunk["module_title"]] = by_module.get(chunk["module_title"], 0) + 1
            if chunk["clauses"]:
                with_clause += 1
        print(f"  chunks carrying a clause id: {with_clause}/{len(chunks)}")
        total = sum(len(c["text"]) for c in chunks)
        print(f"  mean chunk size: {total // max(len(chunks), 1)} chars")
        for module, count in sorted(by_module.items(), key=lambda kv: -kv[1]):
            print(f"  {count:5d}  {module}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
