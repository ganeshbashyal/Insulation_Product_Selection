"""Take manually-supplied datasheets from data/tds_inbox/ and file them against
the families that are missing a source, fully offline.

Why this exists: 184 of 280 researched families carry a spec with no archived
datasheet, so nothing can audit them. The hash-named download cache cannot help
(it is keyed by URL and only ever held the families already linked), and
re-downloading is not an option when the documents were supplied by hand.

Drop files into data/tds_inbox/ - flat, or in per-manufacturer subfolders - and
run this. Matching is by filename against family name/id, so name files close to
the product ("pink-batts-ceiling.pdf"). A subfolder name that matches a
manufacturer restricts matching to that manufacturer, which removes most
ambiguity.

Nothing is guessed: a document is only filed when one family clearly wins, and
every unmatched or ambiguous file is reported so it can be renamed and re-run.

Provenance is recorded in knowledge/_tds_manifest.json, which IS tracked in git
even though the documents themselves are not - so the family/file/SHA-256 link
survives a fresh checkout and this gap cannot silently reopen.

Usage:
    python scripts/ingest_tds_inbox.py                 # dry run, shows matches
    python scripts/ingest_tds_inbox.py --apply         # file them
    python scripts/ingest_tds_inbox.py --apply --min-score 0.75
    python scripts/ingest_tds_inbox.py --relink-only   # rebuild links/manifest

No network access. No cloud services.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import tds_research_agent as tra

INBOX = ROOT / "data" / "tds_inbox"
ARCHIVE = ROOT / "data" / "tds"
MANIFEST = ROOT / "knowledge" / "_tds_manifest.json"

DOC_SUFFIXES = {".pdf", ".docx"}
MIN_TEXT_CHARS = 200

# Filename noise that carries no product meaning and only dilutes similarity.
NOISE = re.compile(
    r"\b(tds|sds|datasheet|data[\s_-]?sheet|technical|specification|spec|brochure"
    r"|product|final|copy|v\d+|rev\d*|\d{4})\b"
)


def normalise(text: str) -> str:
    text = re.sub(r"[_\-]+", " ", text.casefold())
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = NOISE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def looks_like_document(path: Path) -> bool:
    """Reject a mislabelled or truncated file before it is filed as evidence."""
    try:
        head = path.open("rb").read(4)
    except OSError:
        return False
    if path.suffix.casefold() == ".pdf":
        return head.startswith(b"%PDF")
    return head.startswith(b"PK\x03\x04")  # DOCX is a zip


def readable_text(path: Path) -> str:
    try:
        return tra.pdf_text(path, max_pages=12) or ""
    except Exception as exc:  # noqa: BLE001 - a bad file must not kill the run
        print(f"    ! could not read text: {exc}", file=sys.stderr)
        return ""


def load_families() -> list[dict]:
    """Every family that currently has no usable archived datasheet."""
    families = []
    for path in sorted(ROOT.glob("knowledge/*/research/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        local = data.get("datasheet_local_path")
        if local and (ROOT / local).exists():
            continue
        families.append({
            "research_path": path,
            "manufacturer": path.parent.parent.name,
            "slug": path.stem,
            "family_id": data.get("family_id", path.stem),
            "family_name": data.get("family_name") or "",
            "status": data.get("status"),
            "data": data,
        })
    return families


def score(candidate: str, family: dict) -> float:
    """Best similarity of the filename against the family's name, id and slug."""
    targets = [family["family_name"], family["family_id"], family["slug"]]
    best = 0.0
    for target in targets:
        norm = normalise(str(target))
        if not norm:
            continue
        ratio = difflib.SequenceMatcher(None, candidate, norm).ratio()
        # Reward a clean containment ("pink batts ceiling" inside the filename),
        # which SequenceMatcher under-scores when lengths differ a lot.
        if norm and (norm in candidate or candidate in norm):
            ratio = max(ratio, 0.9)
        best = max(best, ratio)
    return best


def pick_match(doc: Path, families: list[dict], min_score: float,
               manufacturer_hint: str | None) -> tuple[dict | None, float, str]:
    candidate = normalise(doc.stem)
    if not candidate:
        return None, 0.0, "filename has no usable text"

    pool = families
    if manufacturer_hint:
        scoped = [f for f in families if f["manufacturer"].casefold() == manufacturer_hint]
        if scoped:
            pool = scoped

    scored = sorted(((score(candidate, f), f) for f in pool), key=lambda x: -x[0])
    if not scored:
        return None, 0.0, "no families awaiting a datasheet"

    best_score, best = scored[0]
    if best_score < min_score:
        return None, best_score, f"best guess {best['family_id']} scored too low"

    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    if best_score - runner_up < 0.05:
        return None, best_score, (
            f"ambiguous between {best['family_id']} and {scored[1][1]['family_id']}"
        )
    return best, best_score, "ok"


def load_manifest() -> dict:
    if MANIFEST.exists():
        try:
            return json.loads(MANIFEST.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"warning: {MANIFEST} unreadable, rebuilding", file=sys.stderr)
    return {}


def write_manifest(entries: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    ordered = {k: entries[k] for k in sorted(entries)}
    MANIFEST.write_text(json.dumps(ordered, indent=2, ensure_ascii=False), encoding="utf-8")


def relink_existing(manifest: dict, apply: bool) -> int:
    """Repair families whose archived file is on disk but unlinked in the JSON.
    This is what makes the gap non-recurring after a fresh checkout."""
    repaired = 0
    for family in load_families():
        archived = ARCHIVE / family["manufacturer"]
        for suffix in DOC_SUFFIXES:
            candidate = archived / f"{family['slug']}{suffix}"
            if not candidate.exists():
                continue
            repaired += 1
            print(f"  relinked {family['family_id']} -> {candidate.relative_to(ROOT)}")
            if apply:
                data = family["data"]
                data["datasheet_local_path"] = str(candidate.relative_to(ROOT))
                family["research_path"].write_text(
                    json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            break
    return repaired


def rebuild_manifest(manifest: dict) -> int:
    """Record every family that has a usable archived datasheet, not just the
    ones touched by this run. The manifest is the tracked record of what
    evidence exists, so it must describe the whole corpus or it is misleading.
    Existing origin values are preserved."""
    seen = 0
    for path in sorted(ROOT.glob("knowledge/*/research/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        local = data.get("datasheet_local_path")
        if not local:
            continue
        full = ROOT / local
        if not full.exists():
            continue
        family_id = data.get("family_id", path.stem)
        prior = manifest.get(family_id, {})
        manifest[family_id] = {
            "manufacturer": path.parent.parent.name,
            "path": str(full.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_of(full),
            "origin": prior.get("origin", data.get("datasheet_source", "researched")),
        }
        if prior.get("inbox_name"):
            manifest[family_id]["inbox_name"] = prior["inbox_name"]
        seen += 1
    return seen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write changes (default is a dry run)")
    parser.add_argument("--min-score", type=float, default=0.62)
    parser.add_argument("--relink-only", action="store_true",
                        help="only repair links for files already in data/tds/")
    args = parser.parse_args()

    INBOX.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()

    if args.relink_only:
        repaired = relink_existing(manifest, args.apply)
        recorded = rebuild_manifest(manifest) if args.apply else 0
        if args.apply:
            write_manifest(manifest)
            print(f"\nrelinked {repaired} families; manifest records {recorded} datasheets")
        else:
            print(f"\nrelinked {repaired} families (dry run, nothing written)")
        return

    docs = [p for p in sorted(INBOX.rglob("*")) if p.is_file() and p.suffix.casefold() in DOC_SUFFIXES]
    if not docs:
        print(f"No .pdf/.docx files in {INBOX.relative_to(ROOT)}. Drop the supplied "
              f"datasheets there (per-manufacturer subfolders help) and re-run.")
        return

    families = load_families()
    print(f"{len(docs)} document(s) in inbox; {len(families)} families awaiting a source\n")

    known_manufacturers = {f["manufacturer"].casefold() for f in families}
    filed = skipped = 0
    claimed: dict[str, Path] = {}
    problems: list[str] = []

    for doc in docs:
        rel = doc.relative_to(INBOX)
        hint = None
        for part in rel.parts[:-1]:
            if part.casefold() in known_manufacturers:
                hint = part.casefold()
                break

        if not looks_like_document(doc):
            problems.append(f"{rel}: not a valid {doc.suffix} (wrong type or truncated)")
            skipped += 1
            continue

        match, confidence, reason = pick_match(doc, families, args.min_score, hint)
        if match is None:
            problems.append(f"{rel}: {reason}")
            skipped += 1
            continue

        if match["family_id"] in claimed:
            problems.append(
                f"{rel}: {match['family_id']} already claimed by {claimed[match['family_id']].name}")
            skipped += 1
            continue

        text = readable_text(doc)
        if len(text) < MIN_TEXT_CHARS:
            problems.append(
                f"{rel}: only {len(text)} chars of extractable text - likely a scan, "
                f"cannot be audited")
            skipped += 1
            continue

        dest_dir = ARCHIVE / match["manufacturer"]
        dest = dest_dir / f"{match['slug']}{doc.suffix.casefold()}"
        print(f"  {rel}\n    -> {match['family_id']}  ({confidence:.2f}, {len(text)} chars)")
        claimed[match["family_id"]] = doc
        filed += 1

        if not args.apply:
            continue

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(doc.read_bytes())
        data = match["data"]
        data["datasheet_local_path"] = str(dest.relative_to(ROOT))
        data["datasheet_source"] = "supplied_manually"
        if data.get("status") != "ok":
            # Keep the old status visible; a supplied document does not by
            # itself prove the spec was ever extracted successfully.
            data["previous_status"] = data.get("status")
        match["research_path"].write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest[match["family_id"]] = {
            "manufacturer": match["manufacturer"],
            "path": str(dest.relative_to(ROOT)),
            "sha256": sha256_of(dest),
            "origin": "supplied_manually",
            "inbox_name": doc.name,
        }

    if args.apply:
        rebuild_manifest(manifest)
        write_manifest(manifest)

    if problems:
        print(f"\nNeeds attention ({len(problems)}):")
        for problem in problems[:40]:
            print(f"  - {problem}")
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more")

    print(f"\nfiled {filed}, skipped {skipped}"
          f"{'' if args.apply else '  (DRY RUN - re-run with --apply to write)'}")
    if args.apply and filed:
        print("\nNext: python scripts/validate_research_accuracy.py --resume --retry-failed")


if __name__ == "__main__":
    main()
