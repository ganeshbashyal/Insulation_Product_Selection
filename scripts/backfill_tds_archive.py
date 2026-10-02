"""Backfill data/tds/<manufacturer>/<family>.pdf for every family whose
research JSON already recorded a verified datasheet_pdf_url but has no
archived local copy (e.g. because data/local/tds_cache was never populated in
this checkout — the cache is gitignored and worktree-local).

Some manufacturers (Autex, Bradford, DCTech, Ecowool...) only recorded a
JavaScript-rendered product *page* as datasheet_pdf_url (the page the earlier
research agent found the spec on), not a direct file link a plain HTTP GET
can retrieve. For those, this script:
  1. fetches the page's raw (pre-JS) HTML and keyword-scans it for any
     embedded PDF/DOCX href (many sites still emit a static download link in
     server-rendered markup even when the rest of the page hydrates via JS);
  2. failing that, falls back to the same keyword site-search + sitemap crawl
     tds_research_agent.search_tds_url() uses to resolve a real family into
     a real document, using the family name as the search keywords.

Pure network re-download/search of already-identity-confirmed families: no
LLM call, no re-extraction. Safe to run repeatedly (skips files already
archived).

Usage:
    python scripts/backfill_tds_archive.py
    python scripts/backfill_tds_archive.py --only Fletcher
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import tds_research_agent as tra
from audit_datasheet_links import OFFICIAL_DOMAINS, domain_matches, domain_of


def _pdf_link_on_page(page_url: str) -> str | None:
    """Keyword-scan a landing page's raw HTML for a same-domain PDF/DOCX link."""
    try:
        html = requests.get(page_url, headers={"User-Agent": tra.USER_AGENT}, timeout=20).text
    except requests.RequestException:
        return None
    domain = domain_of(page_url)
    for link in re.findall(r'href="([^"]+\.(?:pdf|docx)[^"]*)"', html, re.I):
        if link.startswith("//"):
            link = "https:" + link
        elif link.startswith("/"):
            link = f"https://{domain}" + link
        if domain_matches(domain_of(link), [domain]):
            return link
    return None


def _pdf_link_in_next_data(page_url: str) -> str | None:
    """Some Next.js sites server-render a full '__NEXT_DATA__' hydration JSON
    blob that includes document links even though the visible page markup
    doesn't. Scan it for any PDF/DOCX URL as a second, still-cheap tier
    before falling back to external search."""
    try:
        html = requests.get(page_url, headers={"User-Agent": tra.USER_AGENT}, timeout=20).text
    except requests.RequestException:
        return None
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    domain = domain_of(page_url)
    for link in re.findall(r'"(https?://[^"\\]+\.(?:pdf|docx))"', m.group(1), re.I):
        if domain_matches(domain_of(link), [domain]):
            return link
    return None


def _resolve_downloadable_url(manufacturer_dir: str, family_name: str, recorded_url: str) -> str | None:
    """Turn a recorded (possibly JS-rendered landing page) URL into a real
    downloadable document URL, trying the cheapest option first."""
    if recorded_url.lower().split("?")[0].endswith((".pdf", ".docx")):
        return recorded_url
    on_page = _pdf_link_on_page(recorded_url)
    if on_page:
        return on_page
    next_data = _pdf_link_in_next_data(recorded_url)
    if next_data:
        return next_data
    return tra.search_tds_url(manufacturer_dir, family_name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="one manufacturer directory name")
    parser.add_argument("--delay", type=float, default=0.5)
    args = parser.parse_args()

    tally = {"archived": 0, "already_archived": 0, "no_url": 0, "fetch_failed": 0}
    for research_path in sorted(ROOT.glob("knowledge/*/research/*.json")):
        manufacturer_dir = research_path.parent.parent.name
        if args.only and manufacturer_dir.casefold() != args.only.casefold():
            continue
        try:
            data = json.loads(research_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("status") != "ok":
            continue
        if data.get("datasheet_local_path"):
            existing = ROOT / data["datasheet_local_path"]
            if existing.exists():
                tally["already_archived"] += 1
                continue
        url = data.get("datasheet_pdf_url")
        if not url:
            tally["no_url"] += 1
            continue
        downloadable_url = _resolve_downloadable_url(manufacturer_dir, data.get("family_name", ""), url)
        pdf_path = tra.fetch_pdf(downloadable_url) if downloadable_url else None
        if not pdf_path:
            tally["fetch_failed"] += 1
            print(f"  ! fetch failed: {data['family_id']} <- {url}")
            time.sleep(args.delay)
            continue
        slug = research_path.stem
        archived = tra.archive_datasheet(manufacturer_dir, slug, downloadable_url, pdf_path)
        if archived:
            data["datasheet_local_path"] = str(archived.relative_to(ROOT))
            if downloadable_url != url:
                data["datasheet_download_url"] = downloadable_url  # keep original page url as datasheet_pdf_url
            research_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            tally["archived"] += 1
            print(f"  + archived {data['family_id']} -> {archived.relative_to(ROOT)}")
        else:
            tally["fetch_failed"] += 1
        time.sleep(args.delay)

    print("\ntally:", tally)


if __name__ == "__main__":
    main()

