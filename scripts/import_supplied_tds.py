"""Import manually-supplied TDS links from an audit spreadsheet and stage the
documents in data/tds_inbox/ for filing.

The user-supplied workbook lists families that the automated research pass
could not resolve, together with TDS/MSDS links found by hand. This script
matches each row to the family it belongs to, downloads the document straight
from the manufacturer's own site, and drops it into the inbox named after the
family slug.

Deliberately stops there: scripts/ingest_tds_inbox.py already validates the
file type, rejects documents with no extractable text, archives the file and
records provenance in the tracked manifest. Re-implementing that here would
mean two code paths deciding what counts as acceptable evidence.

Only the manufacturer sites are contacted. No cloud or paid services, and the
extraction/validation that follows runs entirely on local models.

Usage:
    python scripts/import_supplied_tds.py                      # dry run
    python scripts/import_supplied_tds.py --apply
    python scripts/import_supplied_tds.py --apply --also-msds  # fall back to MSDS
    python scripts/import_supplied_tds.py --workbook path\\to\\audit.xlsx

Then:
    python scripts/ingest_tds_inbox.py --apply
    python scripts/validate_research_accuracy.py --resume --retry-failed
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ingest_tds_inbox as inbox
import tds_research_agent as tra

DEFAULT_WORKBOOK = Path(r"C:\Users\ganes\Desktop\Aurora-POC\data\raw\Last audit.xlsx")
INBOX = ROOT / "data" / "tds_inbox"

TDS_COL = "TDS Link"
MSDS_COL = "MSDS Link"
MANUFACTURER_COL = "Manufacturer"
FAMILY_COL = "Family Name"


def url_suffix(url: str) -> str:
    path = url.lower().split("?")[0]
    for suffix in (".pdf", ".docx", ".doc"):
        if path.endswith(suffix):
            return ".docx" if suffix == ".doc" else suffix
    return ".pdf"


def shares_a_word(family_name: str, url: str) -> bool:
    """A supplied link whose URL shares no meaningful word with the family is
    often the wrong document (a warranty, or another product's sheet). Not
    fatal, but it must be surfaced rather than silently trusted."""
    words = re.sub(r"[^a-z0-9]+", " ", str(family_name).casefold()).split()
    haystack = re.sub(r"[^a-z0-9]+", " ", str(url).casefold())
    meaningful = [w for w in words if len(w) > 3]
    return not meaningful or any(w in haystack for w in meaningful)


def validated_families(min_score: int = 80) -> dict[str, int]:
    """Families whose current datasheet already passed the local audit. Their
    evidence must not be silently replaced by a spreadsheet link: a supplied
    link is a candidate, not an improvement."""
    report = ROOT / "reports" / "tds_accuracy.json"
    if not report.exists():
        return {}
    try:
        rows = __import__("json").loads(report.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a missing/broken report must not block import
        return {}
    return {
        r["family_id"]: r["accuracy_score"]
        for r in rows
        if isinstance(r.get("accuracy_score"), int) and r["accuracy_score"] >= min_score
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--apply", action="store_true", help="download (default is a dry run)")
    parser.add_argument("--also-msds", action="store_true",
                        help="use the MSDS link when no TDS link is given")
    parser.add_argument("--min-score", type=float, default=0.62)
    parser.add_argument("--replace-validated", action="store_true",
                        help="also replace datasheets that already scored >=80 in the audit")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="seconds between downloads; be polite to manufacturer sites")
    args = parser.parse_args()

    try:
        import pandas as pd
    except ImportError:
        print("pandas is required to read the workbook: pip install pandas openpyxl", file=sys.stderr)
        raise SystemExit(1)

    if not args.workbook.exists():
        print(f"Workbook not found: {args.workbook}", file=sys.stderr)
        raise SystemExit(1)

    frame = pd.read_excel(args.workbook)
    frame.columns = [str(c).strip() for c in frame.columns]
    missing = {MANUFACTURER_COL, FAMILY_COL, TDS_COL} - set(frame.columns)
    if missing:
        print(f"Workbook is missing expected column(s): {sorted(missing)}", file=sys.stderr)
        raise SystemExit(1)

    # Match within the stated manufacturer only. Falling back to every family
    # produces confident nonsense (a Fletcher row matching a Higgins product),
    # so an unknown manufacturer is reported rather than guessed at.
    families = inbox.load_families(include_sourced=True)
    by_manufacturer: dict[str, list[dict]] = {}
    for family in families:
        by_manufacturer.setdefault(family["manufacturer"].casefold(), []).append(family)

    awaiting = sum(1 for f in families if not f["has_source"])
    print(f"{len(frame)} rows; {len(families)} families ({awaiting} still without a source)\n")

    staged = 0
    suspect: list[str] = []
    problems: list[str] = []
    claimed: set[str] = set()
    protected = {} if args.replace_validated else validated_families()
    urls_seen: dict[str, str] = {}
    if protected:
        print(f"protecting {len(protected)} families that already scored >=80\n")

    for _, row in frame.iterrows():
        family_name = str(row.get(FAMILY_COL) or "").strip()
        manufacturer = str(row.get(MANUFACTURER_COL) or "").strip()
        label = f"{manufacturer}/{family_name}"

        url = row.get(TDS_COL)
        source_kind = "TDS"
        if (not isinstance(url, str) or not url.strip()) and args.also_msds:
            url = row.get(MSDS_COL)
            source_kind = "MSDS"
        if not isinstance(url, str) or not url.strip():
            problems.append(f"{label}: no link supplied")
            continue
        url = url.strip()

        pool = by_manufacturer.get(manufacturer.casefold())
        if not pool:
            problems.append(f"{label}: no families under manufacturer '{manufacturer}'")
            continue
        candidate = inbox.normalise(family_name)
        if not candidate:
            problems.append(f"{label}: family name unusable for matching")
            continue

        scored = sorted(((inbox.score(candidate, f), f) for f in pool), key=lambda x: -x[0])
        if not scored or scored[0][0] < args.min_score:
            best = f" (best {scored[0][1]['family_id']} @ {scored[0][0]:.2f})" if scored else ""
            problems.append(f"{label}: no family match{best}")
            continue

        confidence, match = scored[0]
        if match["family_id"] in claimed:
            problems.append(f"{label}: {match['family_id']} already staged from another row")
            continue

        if match["family_id"] in protected:
            problems.append(
                f"{label}: current datasheet already scored "
                f"{protected[match['family_id']]}; not replacing "
                f"(use --replace-validated to override)")
            continue

        related = shares_a_word(family_name, url)

        # A shared URL is normal for variants of one product - Autex publishes
        # a single Horizon datasheet covering every shape. It is only a real
        # error when the link also has nothing to do with the family name,
        # which is how a copy-paste mistake looks.
        if url in urls_seen and not related:
            suspect.append(
                f"{match['family_id']}: unrelated link already used for "
                f"{urls_seen[url]} -> {url}")
            problems.append(
                f"{label}: link appears unrelated and duplicates {urls_seen[url]}")
            continue
        shared_with = urls_seen.get(url)
        urls_seen.setdefault(url, match["family_id"])

        if not related:
            suspect.append(f"{match['family_id']}: link looks unrelated -> {url}")

        dest_dir = INBOX / match["manufacturer"]
        dest = dest_dir / f"{match['slug']}{url_suffix(url)}"
        claimed.add(match["family_id"])
        staged += 1
        action = "replaces existing" if match["has_source"] else "new source"
        if shared_with:
            action += f", shares datasheet with {shared_with}"
        print(f"  {label}\n    -> {match['family_id']} ({confidence:.2f}) [{source_kind}, {action}]")

        if not args.apply:
            continue

        cached = tra.fetch_pdf(url)
        if cached is None:
            problems.append(f"{label}: download failed or not a real document -> {url}")
            claimed.discard(match["family_id"])
            staged -= 1
            continue

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(cached.read_bytes())
        # Record where this came from so the family is traceable to the
        # supplied link, not just to a file that appeared in the inbox.
        data = match["data"]
        data["datasheet_pdf_url"] = url
        data["datasheet_source"] = f"supplied_{source_kind.casefold()}_link"
        match["research_path"].write_text(
            __import__("json").dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        time.sleep(args.delay)

    if suspect:
        print(f"\nCheck these by hand ({len(suspect)}) - the URL does not mention the product:")
        for item in suspect:
            print(f"  - {item}")

    if problems:
        print(f"\nNot staged ({len(problems)}):")
        for problem in problems[:40]:
            print(f"  - {problem}")
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more")

    print(f"\nstaged {staged}"
          f"{'' if args.apply else '  (DRY RUN - re-run with --apply to download)'}")
    if args.apply and staged:
        print("\nNext: python scripts/ingest_tds_inbox.py --apply")


if __name__ == "__main__":
    main()
