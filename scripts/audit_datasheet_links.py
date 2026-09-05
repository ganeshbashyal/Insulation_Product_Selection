"""Audit manufacturer datasheet links across all product families.

Every family in knowledge/<manufacturer>/families.json carries a source_url
that is supposed to be the manufacturer's own Technical Data Sheet. The first
deep-dive pass inherited URLs from the master spreadsheet, many of which point
at reseller/aggregator sites (pricewiseinsulation.com.au, archiclad.com.au,
insulationvictoria.com.au, ...) or at the wrong manufacturer entirely.

This audit classifies each link:
  OK_OFFICIAL        domain belongs to the manufacturer (verified live 2026-09-05)
  OK_BUT_DEAD        official domain, but the URL itself does not resolve (HTTP error)
  WRONG_DOMAIN       reseller/aggregator or unrelated domain
  MISSING            no URL recorded / placeholder
  UNVERIFIED_MFR     manufacturer whose official domain could not be confirmed

It also performs a threaded HTTP liveness check on every link and writes the
full results to data/processed/datasheet_audit.csv.

Usage:
    python scripts/audit_datasheet_links.py              # domain audit + live link check
    python scripts/audit_datasheet_links.py --no-http    # domain audit only (fast, offline)
"""
from __future__ import annotations

import argparse
import csv
import json
import ssl
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
OUT_CSV = ROOT / "data" / "processed" / "datasheet_audit.csv"

# Official manufacturer domains, verified live on 2026-09-05 unless noted.
OFFICIAL_DOMAINS = {
    "acoustica": ["acoustica.com.au"],
    "aircell": ["kingspan.com"],  # AIR-CELL is a Kingspan brand
    "ametalin": ["ametalin.com"],
    "autex": ["autexacoustics.com.au", "autexacoustics.co.nz", "autex.com.au", "autexglobal.com"],
    "bradford": ["csrbradford.com.au", "bradfordinsulation.com.au"],
    "dctech": ["dctech.com.au"],
    "ecowool": ["ecowool-insulation.com", "ecowool.com.au"],  # unverified from audit environment
    "fletcher": ["insulation.com.au"],
    "foilboard": ["foilboard.com", "foilboard.com.au"],
    "higgins insulation": ["higginsinsulation.com.au"],
    "hushtec": ["hushtec.com.au"],  # unverified from audit environment
    "james hardie": ["jameshardie.com.au"],
    "kingspan": ["kingspan.com"],
    "knauf": ["knauf.com", "knaufinsulation.com.au", "earthwool.com.au"],
    "martini": ["martini.com.au"],
    "metecno": ["metecno.com"],
    "misc": [],  # mixed brands - every link needs individual review
    "paroc": ["paroc.com"],
    "polyair": ["polyair.com.au"],
    "polyester solutions": ["polyestersolutions.com.au"],
    "proctor": ["proctorgroup.com.au"],
    "rockwool": ["rockwool.com"],
    "sonata acoustic panels": ["sonataacousticpanels.com.au"],
    "stinger": ["insulation.com.au"],  # Fletcher-distributed brand
    "thermotec": ["thermotec.com.au"],
    "trade select": ["tradeselect.com.au", "ametalin.com"],  # Trade Select is an Ametalin brand
}
UNVERIFIED_MANUFACTURERS = {"ecowool", "hushtec"}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) datasheet-audit/1.0"


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def domain_matches(domain: str, official: list[str]) -> bool:
    return any(domain == o or domain.endswith("." + o) for o in official)


def http_status(url: str, timeout: float = 8.0) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(request, timeout=timeout, context=ctx) as response:
            return str(response.status)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 405, 501):
            # Some CDNs reject HEAD; retry once as a minimal GET.
            try:
                get = urllib.request.Request(url, headers={**dict(request.header_items()), "Range": "bytes=0-0"})
                with urllib.request.urlopen(get, timeout=timeout, context=ssl.create_default_context()) as response:
                    return str(response.status)
            except Exception as exc2:  # noqa: BLE001 - record whatever happened
                return f"{exc.code} (GET retry: {type(exc2).__name__})"
        return str(exc.code)
    except Exception as exc:  # noqa: BLE001 - URLError, timeout, ssl, ...
        return type(exc).__name__


def classify(manufacturer: str, url: str) -> str:
    if not url or url.strip() in ("", "[To be sourced]"):
        return "MISSING"
    official = OFFICIAL_DOMAINS.get(manufacturer)
    if official is None:
        return "UNVERIFIED_MFR"
    if not official:
        return "UNVERIFIED_MFR"
    if domain_matches(domain_of(url), official):
        return "UNVERIFIED_MFR" if manufacturer in UNVERIFIED_MANUFACTURERS else "OK_OFFICIAL"
    if manufacturer in UNVERIFIED_MANUFACTURERS:
        return "UNVERIFIED_MFR"
    return "WRONG_DOMAIN"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-http", action="store_true", help="skip live link checks")
    args = parser.parse_args()

    rows = []
    for path in sorted(ROOT.glob("knowledge/*/families.json")):
        manufacturer = path.parent.name
        for family in json.loads(path.read_text(encoding="utf-8"))["families"]:
            url = (family.get("source_url") or "").strip()
            rows.append({
                "manufacturer": manufacturer,
                "family_id": family["family_id"],
                "family_name": family["name"],
                "source_url": url,
                "domain": domain_of(url) if url else "",
                "domain_status": classify(manufacturer, url),
                "http_status": "",
            })

    if not args.no_http:
        urls = sorted({row["source_url"] for row in rows if row["source_url"] and row["source_url"] != "[To be sourced]"})
        print(f"checking {len(urls)} unique URLs ...")
        with ThreadPoolExecutor(max_workers=16) as pool:
            statuses = dict(zip(urls, pool.map(http_status, urls)))
        for row in rows:
            row["http_status"] = statuses.get(row["source_url"], "")
        for row in rows:
            if row["domain_status"] == "OK_OFFICIAL" and row["http_status"] and row["http_status"] not in ("200", "206", "301", "302"):
                row["domain_status"] = "OK_BUT_DEAD"

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nwrote {OUT_CSV.relative_to(ROOT)} ({len(rows)} families)\n")
    header = f"{'status':<15} {'families':>8}"
    print(header)
    print("-" * len(header))
    from collections import Counter
    counts = Counter(row["domain_status"] for row in rows)
    for status, count in counts.most_common():
        print(f"{status:<15} {count:>8}")
    print("\nby manufacturer (non-OK only):")
    by_mfg = Counter((row["manufacturer"], row["domain_status"]) for row in rows if row["domain_status"] != "OK_OFFICIAL")
    for (mfg, status), count in sorted(by_mfg.items()):
        print(f"  {mfg:<24} {status:<15} {count}")


if __name__ == "__main__":
    main()
