"""Download manufacturer TDS PDFs listed in data/local/tds_url_review.csv.

This is the only script in this pipeline that actually reaches the open
internet - and even then, only to fetch public PDF files via a plain HTTP
GET (urllib.request, no third-party SDK). It does NOT call any AI model and
does NOT spend Copilot/cloud-LLM credits: downloading a file is the same
action as clicking a link in a browser, just scripted.

Run scripts/compile_tds_url_list.py first to (re)generate the CSV this reads.

Usage
-----
    python -m scripts.download_tds_pdfs --dry-run
    python -m scripts.download_tds_pdfs
    python -m scripts.download_tds_pdfs --tier primary --domain-type all
    python -m scripts.download_tds_pdfs --manufacturer bradford,kingspan

Defaults are deliberately conservative: only rows tagged download_tier=primary
(deduped, one link per manufacturer) AND domain_type=manufacturer_domain
(hosted on a domain the manufacturer's own source_url already uses) are
fetched, unless you widen the scope with --tier/--domain-type/--all.

Writes each PDF to data/tds/<manufacturer>/<family_id>.pdf and a status
summary to data/local/tds_download_status.json (one entry per attempted row:
outcome, HTTP status, bytes written, error if any) so a human running this
locally can see exactly what happened without re-reading terminal scrollback.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "local" / "tds_url_review.csv"
DEFAULT_OUT_DIR = ROOT / "data" / "tds"
DEFAULT_STATUS_PATH = ROOT / "data" / "local" / "tds_download_status.json"

#: A real-looking UA string - many manufacturer/reseller sites block the
#: default urllib UA ("Python-urllib/3.x") outright.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(text: str) -> str:
    return _SAFE_NAME_RE.sub("_", text.strip()).strip("_") or "unnamed"


def _load_rows(csv_path: Path) -> list[dict]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _select_rows(
    rows: list[dict],
    tier: str,
    domain_type: str,
    manufacturers: set[str] | None,
) -> list[dict]:
    selected = []
    for row in rows:
        if not row.get("candidate_url"):
            continue
        if tier != "all" and row.get("download_tier") != tier:
            continue
        if domain_type != "all" and row.get("domain_type") != domain_type:
            continue
        if manufacturers and row.get("manufacturer", "").lower() not in manufacturers:
            continue
        selected.append(row)
    return selected


def _download_one(row: dict, out_dir: Path, timeout: float) -> dict:
    url = row["candidate_url"]
    manufacturer_dir = out_dir / _safe_filename(row["manufacturer"])
    filename = _safe_filename(row.get("family_id") or row.get("family_name") or "unnamed") + ".pdf"
    dest = manufacturer_dir / filename

    result = {
        "manufacturer": row["manufacturer"],
        "family_id": row.get("family_id", ""),
        "family_name": row.get("family_name", ""),
        "url": url,
        "dest": str(dest),
        "outcome": "pending",
        "http_status": None,
        "bytes_written": 0,
        "error": None,
    }

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result["http_status"] = getattr(response, "status", None) or response.getcode()
            content_type = response.headers.get("Content-Type", "")
            body = response.read()
    except urllib.error.HTTPError as error:
        result["outcome"] = "failed"
        result["http_status"] = error.code
        result["error"] = f"HTTP {error.code}: {error.reason}"
        return result
    except urllib.error.URLError as error:
        result["outcome"] = "failed"
        result["error"] = f"connection error: {error.reason}"
        return result
    except TimeoutError:
        result["outcome"] = "failed"
        result["error"] = f"timed out after {timeout}s"
        return result

    if b"%PDF" not in body[:1024] and "pdf" not in content_type.lower():
        result["outcome"] = "warn_not_pdf"
        result["error"] = f"response does not look like a PDF (content-type: {content_type or 'unknown'})"
        # Still write it - a human can inspect it - but the warning is visible.

    manufacturer_dir.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    result["bytes_written"] = len(body)
    if result["outcome"] == "pending":
        result["outcome"] = "ok"
    return result


def run(
    csv_path: Path = DEFAULT_CSV,
    out_dir: Path = DEFAULT_OUT_DIR,
    tier: str = "primary",
    domain_type: str = "manufacturer_domain",
    manufacturers: set[str] | None = None,
    delay: float = 1.5,
    timeout: float = 20.0,
    dry_run: bool = False,
) -> list[dict]:
    if not csv_path.exists():
        raise FileNotFoundError(f"{csv_path} not found - run scripts/compile_tds_url_list.py first.")

    rows = _select_rows(_load_rows(csv_path), tier=tier, domain_type=domain_type, manufacturers=manufacturers)
    if not rows:
        print("No rows matched the selected tier/domain-type/manufacturer filters. Nothing to do.")
        return []

    print(f"{len(rows)} PDF(s) selected (tier={tier}, domain_type={domain_type}).")
    if dry_run:
        for row in rows:
            print(f"  [DRY-RUN] {row['manufacturer']} / {row['family_name']} -> {row['candidate_url']}")
        return []

    results = []
    for index, row in enumerate(rows, start=1):
        result = _download_one(row, out_dir, timeout=timeout)
        tag = {"ok": "[OK]", "warn_not_pdf": "[WARN]", "failed": "[FAIL]"}.get(result["outcome"], "[?]")
        print(f"  [{index}/{len(rows)}] {tag} {row['manufacturer']} / {row['family_name']}")
        if result["error"]:
            print(f"        {result['error']}")
        results.append(result)
        if index < len(rows):
            time.sleep(delay)

    ok = sum(1 for r in results if r["outcome"] == "ok")
    warn = sum(1 for r in results if r["outcome"] == "warn_not_pdf")
    failed = sum(1 for r in results if r["outcome"] == "failed")
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "csv_source": str(csv_path),
        "out_dir": str(out_dir),
        "tier": tier,
        "domain_type": domain_type,
        "requested": len(rows),
        "ok": ok,
        "warn_not_pdf": warn,
        "failed": failed,
        "files": results,
    }
    DEFAULT_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_STATUS_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSummary: {ok} ok, {warn} warn (not a PDF), {failed} failed. Status written to {DEFAULT_STATUS_PATH}.")
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="input CSV from compile_tds_url_list.py")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="folder to save PDFs into (per-manufacturer subfolders)")
    parser.add_argument("--tier", default="primary", choices=["primary", "duplicate_link", "needs_human_url", "all"], help="download_tier filter (default: primary)")
    parser.add_argument("--domain-type", default="manufacturer_domain", choices=["manufacturer_domain", "third_party", "unknown", "all"], help="domain_type filter (default: manufacturer_domain)")
    parser.add_argument("--manufacturer", default="", help="comma-separated manufacturer folder names to restrict to, e.g. bradford,kingspan")
    parser.add_argument("--delay", type=float, default=1.5, help="seconds to wait between downloads (politeness delay)")
    parser.add_argument("--timeout", type=float, default=20.0, help="per-request timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="list what would be downloaded without fetching anything")
    args = parser.parse_args(argv)

    manufacturers = {m.strip().lower() for m in args.manufacturer.split(",") if m.strip()} or None

    results = run(
        csv_path=Path(args.csv),
        out_dir=Path(args.out_dir),
        tier=args.tier,
        domain_type=args.domain_type,
        manufacturers=manufacturers,
        delay=args.delay,
        timeout=args.timeout,
        dry_run=args.dry_run,
    )
    if args.dry_run:
        return 0
    if not results:
        return 1
    return 2 if any(r["outcome"] == "failed" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
