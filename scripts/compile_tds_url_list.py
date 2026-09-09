"""Compile a reviewable list of manufacturer TDS URLs from families.json.

Pure local operation: reads knowledge/*/families.json already on disk and
writes a CSV (data/local/tds_url_review.csv) for human review before any
download is considered. No network access of any kind.

The output CSV has one row per family, with enough context to spot-check:
  family_id, manufacturer, family name, current source_url, legacy_source_url,
  source_url_status, and a derived 'candidate_url' column (the best guess for
  what to actually fetch, preferring a direct .pdf link over a site root).
It also flags 'download_tier' (primary/duplicate_link/needs_human_url) and
'domain_type' (manufacturer_domain/third_party/unknown) so a human reviewer
can prioritise the manufacturer's own PDFs over reseller-hosted copies.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "local" / "tds_url_review.csv"

#: Australian ccTLD second-level suffixes where the registrable domain needs
#: three labels (e.g. "csrbradford.com.au"), not the usual two.
_AU_SECOND_LEVEL = {"com.au", "net.au", "org.au", "gov.au", "edu.au", "asn.au", "id.au"}


def _registrable_domain(netloc: str) -> str:
    """Best-effort registrable domain, e.g. 'www.csrbradford.com.au' -> 'csrbradford.com.au'."""
    host = netloc.split(":")[0].lower()
    labels = host.split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in _AU_SECOND_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def _iter_families():
    for path in sorted((ROOT / "knowledge").glob("*/families.json")):
        manufacturer = path.parent.name
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("families", data.get("items", []))
        for item in items:
            yield manufacturer, item


def _known_domains_per_manufacturer(rows: list[dict]) -> dict[str, set[str]]:
    """The registrable domains seen in each manufacturer's own source_url field.

    This is the closest thing to a manufacturer's "official domain" already
    present in our local data - no network lookup needed.
    """
    known: dict[str, set[str]] = {}
    for row in rows:
        if not row["source_url"]:
            continue
        domain = _registrable_domain(urlparse(row["source_url"]).netloc)
        if domain:
            known.setdefault(row["manufacturer"], set()).add(domain)
    return known


def main() -> None:
    rows = []
    for manufacturer, item in _iter_families():
        source_url = (item.get("source_url") or "").strip()
        legacy_url = (item.get("legacy_source_url") or "").strip()
        status = item.get("source_url_status") or ""

        if legacy_url.lower().endswith(".pdf"):
            candidate = legacy_url
        elif source_url.lower().endswith(".pdf"):
            candidate = source_url
        else:
            candidate = ""  # site root only - needs a human to find the real TDS

        rows.append({
            "family_id": item.get("family_id", ""),
            "manufacturer": manufacturer,
            "family_name": item.get("name", ""),
            "source_url": source_url,
            "legacy_source_url": legacy_url,
            "source_url_status": status,
            "candidate_url": candidate,
        })

    # Domain classification: is the candidate PDF hosted on a domain the
    # manufacturer itself uses (per its own source_url), or a third-party /
    # reseller site? Purely a spot-check aid, not a guarantee of ownership.
    known_domains = _known_domains_per_manufacturer(rows)
    for row in rows:
        if not row["candidate_url"]:
            row["domain_type"] = "unknown"
            continue
        candidate_domain = _registrable_domain(urlparse(row["candidate_url"]).netloc)
        manufacturer_domains = known_domains.get(row["manufacturer"], set())
        row["domain_type"] = "manufacturer_domain" if candidate_domain in manufacturer_domains else "third_party"

    # Dedupe pass: a single PDF shared across many families of the same
    # manufacturer is almost certainly a generic datasheet, not a per-product
    # TDS. Mark only the first family per (manufacturer, candidate_url) as a
    # primary download target; the rest are flagged as "duplicate_link".
    seen: dict[tuple[str, str], bool] = {}
    for row in rows:
        key = (row["manufacturer"], row["candidate_url"])
        if not row["candidate_url"]:
            row["download_tier"] = "needs_human_url"   # no direct .pdf at all
        elif seen.get(key):
            row["download_tier"] = "duplicate_link"    # shared generic datasheet
        else:
            row["download_tier"] = "primary"           # unique-ish per-product link
            seen[key] = True

    tier_rank = {"primary": 0, "duplicate_link": 1, "needs_human_url": 2}
    domain_rank = {"manufacturer_domain": 0, "third_party": 1, "unknown": 2}
    rows.sort(key=lambda r: (tier_rank[r["download_tier"]], domain_rank[r["domain_type"]], r["manufacturer"], r["family_name"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    primary = sum(1 for r in rows if r["download_tier"] == "primary")
    duplicate = sum(1 for r in rows if r["download_tier"] == "duplicate_link")
    needs_human = sum(1 for r in rows if r["download_tier"] == "needs_human_url")
    manufacturer_owned = sum(1 for r in rows if r["domain_type"] == "manufacturer_domain")
    third_party = sum(1 for r in rows if r["domain_type"] == "third_party")
    primary_manufacturer_owned = sum(1 for r in rows if r["download_tier"] == "primary" and r["domain_type"] == "manufacturer_domain")
    print(f"Wrote {len(rows)} rows to {OUT}")
    print(f"  {primary} primary (unique per-manufacturer PDF link, plausible per-product TDS)")
    print(f"  {duplicate} duplicate_link (same generic datasheet shared across families - skipped)")
    print(f"  {needs_human} needs_human_url (no direct .pdf - needs a human to find the real TDS)")
    print(f"  --- domain check ---")
    print(f"  {manufacturer_owned} candidate URLs hosted on the manufacturer's own domain")
    print(f"  {third_party} candidate URLs hosted on a third-party/reseller domain")
    print(f"  {primary_manufacturer_owned}/{primary} of the 'primary' rows are manufacturer-owned domains")


if __name__ == "__main__":
    main()
