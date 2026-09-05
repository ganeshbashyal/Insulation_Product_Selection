"""Deep-dive research agent: fetch real manufacturer datasheets and populate
rich product literature for every family.

Pipeline per family (runs locally, resumable):
  1. resolve   - find the TDS/SDS URL: use the confirmed source_url, else
                 search the manufacturer's own site (DuckDuckGo site: query,
                 no API key) for a datasheet PDF on the official domain
  2. fetch     - download the PDF to data/local/tds_cache/ (cached by URL)
  3. extract   - pull text with pypdf
  4. structure - ask the LOCAL Ollama model to extract a strict JSON spec
                 (description, features, technical table, applications,
                 install, fire, sustainability). No data leaves the machine.
  5. write     - store the structured spec to knowledge/<mfg>/research/<slug>.json

After research, run scripts/generate_family_literature.py --use-research to
regenerate the MD/DOCX from the real extracted data instead of thin catalogue
placeholders.

Usage:
    python scripts/tds_research_agent.py --only Thermotec     # one manufacturer
    python scripts/tds_research_agent.py --limit 5            # first 5 families
    python scripts/tds_research_agent.py                      # all, resumable
    python scripts/tds_research_agent.py --status             # progress report
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pypdf
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm_client
from audit_datasheet_links import OFFICIAL_DOMAINS, domain_matches, domain_of

CACHE_DIR = ROOT / "data" / "local" / "tds_cache"
RESEARCH_DIR_NAME = "research"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) tds-research/1.0"

EXTRACT_PROMPT = """You are extracting structured product data from an insulation Technical Data Sheet.

Return ONLY a JSON object (no markdown fences, no commentary) with these keys:
  "description": 1-2 sentence factual product description.
  "features": list of up to 8 short feature strings.
  "applications": list of applications (e.g. "ceiling", "external wall").
  "technical": list of {"property","value","standard"} objects for every spec found (R-value, density, thickness, thermal conductivity, fire indices, temperature range, vapour, dimensions). Use "" for standard if none stated.
  "fire": short string of fire/AS-NZS 1530.3 results, or "" if none.
  "sustainability": short string of recycled-content/VOC/environmental claims, or "" if none.
  "install": list of up to 8 short installation steps, or [] if none.

Rules: only report values actually present in the text. Never invent numbers. If a field is absent use "" or []. Keep numbers and units exactly as written.

TDS TEXT:
"""


def slugify(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()[:60]


_SKU_PDFS: dict[str, str] | None = None


def _sku_pdf_url(family_id: str, official: list[str]) -> str | None:
    """Official TDS PDF already recorded in the SKU catalogue for this family."""
    global _SKU_PDFS
    if _SKU_PDFS is None:
        _SKU_PDFS = {}
        import pandas as pd
        csv_path = ROOT / "data" / "processed" / "product_catalogue_skus.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path).fillna("")
            for _, row in df.iterrows():
                url = str(row["tds_url"]).strip()
                if url.lower().endswith(".pdf") and row["family_id"] not in _SKU_PDFS:
                    _SKU_PDFS[row["family_id"]] = url
    url = _SKU_PDFS.get(family_id)
    if url and domain_matches(domain_of(url), official):
        return url
    return None


def research_path(manufacturer_dir: str, slug: str) -> Path:
    return ROOT / "knowledge" / manufacturer_dir / RESEARCH_DIR_NAME / f"{slug}.json"


def fetch_pdf(url: str) -> Path | None:
    """Download a PDF to the cache; return its path or None."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    name = hashlib_name(url) + ".pdf"
    target = CACHE_DIR / name
    if target.exists() and target.stat().st_size > 1000:
        return target
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30, stream=True)
        if response.status_code != 200:
            return None
        content = response.content
        if not content.startswith(b"%PDF"):
            return None
        target.write_bytes(content)
        return target
    except Exception:
        return None


def hashlib_name(url: str) -> str:
    import hashlib
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def pdf_text(path: Path, max_pages: int = 12) -> str:
    try:
        reader = pypdf.PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages[:max_pages]]
        return "\n".join(pages)
    except Exception:
        return ""


def search_tds_url(manufacturer: str, family_name: str) -> str | None:
    """Find a datasheet PDF on the manufacturer's own domain.

    Tries, in order: the site search engines (DuckDuckGo HTML, Bing), then a
    sitemap crawl of the official domain looking for PDF links whose path
    matches the family name. Search engines may be blocked in some
    environments; the sitemap crawl is the reliable fallback.
    """
    official = OFFICIAL_DOMAINS.get(manufacturer) or []
    if not official:
        return None
    domain = official[0]
    family_terms = [t for t in re.findall(r"[a-z0-9]+", family_name.casefold()) if len(t) > 3 and t != manufacturer.casefold()]

    def matches(url: str) -> bool:
        path = urllib.parse.urlparse(url).path.casefold()
        return bool(family_terms) and any(term in path for term in family_terms)

    for engine_url in (
        "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(f"site:{domain} {family_name} filetype:pdf"),
        "https://www.bing.com/search?q=" + urllib.parse.quote(f"site:{domain} {family_name} filetype:pdf"),
    ):
        try:
            response = requests.get(engine_url, headers={"User-Agent": USER_AGENT}, timeout=20)
            for link in re.findall(r'href="([^"]+\.pdf[^"]*)"', response.text, re.I):
                link = "https:" + link if link.startswith("//") else link
                if domain_matches(domain_of(link), official) and matches(link):
                    return link
        except Exception:
            continue

    # sitemap fallback: walk the official domain's sitemap(s) for product/PDF URLs
    try:
        return _sitemap_pdf(domain, family_terms, matches)
    except Exception:
        return None


def _sitemap_pdf(domain: str, family_terms: list[str], matches) -> str | None:
    seen: set[str] = set()
    queue = [f"https://{domain}/sitemap.xml", f"https://www.{domain}/sitemap.xml"]
    product_pages: list[str] = []
    for _ in range(6):  # bounded crawl
        if not queue:
            break
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        try:
            xml = requests.get(sm, headers={"User-Agent": USER_AGENT}, timeout=20).text
        except Exception:
            continue
        locs = re.findall(r"<loc>([^<]+)</loc>", xml)
        for loc in locs:
            low = loc.casefold()
            if low.endswith(".pdf") and matches(loc):
                return loc
            if low.endswith(".xml"):
                queue.append(loc)
            elif matches(loc):
                product_pages.append(loc)
    # fetch a few candidate product pages and look for a linked PDF
    for page in product_pages[:5]:
        try:
            html = requests.get(page, headers={"User-Agent": USER_AGENT}, timeout=20).text
        except Exception:
            continue
        for link in re.findall(r'href="([^"]+\.pdf[^"]*)"', html, re.I):
            if link.startswith("/"):
                link = f"https://{domain}" + link
            if domain_matches(domain_of(link), [domain]):
                return link
    return None


def extract_spec(text: str) -> dict | None:
    """Ask the local Ollama model to structure the TDS text into JSON."""
    if not llm_client.ollama_available():
        return None
    trimmed = text[:10000]  # leave headroom for the JSON reply in context
    for attempt in range(3):
        raw = _generate_json(trimmed)
        if raw:
            spec = _parse_spec(raw)
            if spec is not None:
                return spec
        time.sleep(2 * (attempt + 1))  # back off; cold model loads can drop a call
    return None


def _generate_json(text: str) -> str | None:
    """Direct Ollama call tuned for deterministic JSON: temperature 0 and a
    large num_predict, unlike the chat phrasing defaults in llm_client."""
    payload = {
        "model": llm_client.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": "You extract structured JSON from technical datasheets. Output only valid JSON, no markdown fences, no commentary."},
            {"role": "user", "content": EXTRACT_PROMPT + text},
        ],
        "stream": False,
        "think": False,
        "keep_alive": "30m",
        "options": {"temperature": 0, "num_predict": 2000, "num_ctx": 8192},
    }
    request = urllib.request.Request(
        f"{llm_client.OLLAMA_HOST}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    return (data.get("message") or {}).get("content", "").strip() or None


def _parse_spec(raw: str) -> dict | None:
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return None
    candidate = match.group(0)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    # truncated output: try progressively closing open arrays/object
    for closers in ('"]}', '"}]', "]}", "}", "]}"):
        try:
            return json.loads(candidate + closers)
        except json.JSONDecodeError:
            continue
    return None


def process_family(manufacturer_dir: str, family: dict, delay: float = 1.0) -> str:
    slug = slugify(family["name"])
    out_path = research_path(manufacturer_dir, slug)
    if out_path.exists():
        try:
            if json.loads(out_path.read_text(encoding="utf-8")).get("status") == "ok":
                return "cached"
        except (json.JSONDecodeError, OSError):
            pass  # corrupt file: reprocess

    tds_url = (family.get("source_url") or "").strip()
    official = OFFICIAL_DOMAINS.get(manufacturer_dir) or []
    on_official = tds_url and domain_matches(domain_of(tds_url), official)

    # resolve a PDF URL. Preference order:
    #   1. an official TDS PDF already in the SKU catalogue for this family
    #   2. the family's own source_url if it is already an official PDF
    #   3. a web search on the manufacturer's domain (needs open internet)
    pdf_url = _sku_pdf_url(family["family_id"], official)
    if pdf_url is None and tds_url.lower().endswith(".pdf") and on_official:
        pdf_url = tds_url
    if pdf_url is None:
        pdf_url = search_tds_url(manufacturer_dir, family["name"])
        time.sleep(delay)  # be polite to search

    if not pdf_url:
        _write(out_path, family, None, None, None, "no_pdf_found")
        return "no_pdf"

    pdf_path = fetch_pdf(pdf_url)
    if not pdf_path:
        _write(out_path, family, pdf_url, None, None, "pdf_fetch_failed")
        return "fetch_failed"

    text = pdf_text(pdf_path)
    if len(text) < 200:
        _write(out_path, family, pdf_url, None, None, "pdf_no_text")
        return "no_text"

    spec = extract_spec(text)
    if spec is None:
        _write(out_path, family, pdf_url, None, None, "extract_failed")
        return "extract_failed"

    _write(out_path, family, pdf_url, spec, text[:2000], "ok")
    return "ok"


def _write(out_path: Path, family: dict, pdf_url: str | None, spec: dict | None, excerpt: str | None, status: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "family_id": family["family_id"],
        "family_name": family["name"],
        "datasheet_pdf_url": pdf_url,
        "status": status,
        "researched_at": time.strftime("%Y-%m-%d"),
        "spec": spec,
        "source_excerpt": excerpt,
    }, indent=2, ensure_ascii=False), encoding="utf-8")


def status_report() -> None:
    counts: dict[str, int] = {}
    for path in sorted(ROOT.glob("knowledge/*/research/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        counts[data["status"]] = counts.get(data["status"], 0) + 1
    total = sum(counts.values())
    print(f"researched families: {total}")
    for status, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {status:<16} {count}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="one manufacturer directory name")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.status:
        status_report()
        return

    if not llm_client.ollama_available():
        print("WARNING: local Ollama not detected - extraction will fail. Start 'ollama serve' first.")

    done = 0
    tally: dict[str, int] = {}
    for path in sorted(ROOT.glob("knowledge/*/families.json")):
        manufacturer_dir = path.parent.name
        if args.only and manufacturer_dir.casefold() != args.only.casefold():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for family in data["families"]:
            family.setdefault("manufacturer", manufacturer_dir.title())
            if args.limit and done >= args.limit:
                break
            result = process_family(manufacturer_dir, family, delay=args.delay)
            tally[result] = tally.get(result, 0) + 1
            done += 1
            if result != "cached":
                print(f"[{done}] {family['name'][:50]:<52} {result}")
        if args.limit and done >= args.limit:
            break

    print("\ntally:", tally)


if __name__ == "__main__":
    main()
