"""Recover datasheets for families whose research recorded a product page
instead of a document.

118 families carry a spec with no retained source because the URL captured
during research points at a manufacturer's product page, not a PDF. Those
pages usually still link the real datasheet.

For each such family this fetches its page, finds linked PDF/DOCX documents,
and works out which one belongs to the family:

  one document on the page   -> it is the family's datasheet
  several documents          -> score their filenames against the family name
  still unclear              -> read each document's text and ask the local
                                model which product it describes

Only the manufacturer's own site is contacted, and identification runs on the
local Ollama model. Downloads go straight into the external TDS library so the
same document is never fetched twice, then into data/tds_inbox/ for the
existing validation and filing path.

Usage:
    python scripts/resolve_tds_from_page.py --limit 5        # dry run pilot
    python scripts/resolve_tds_from_page.py --apply
    python scripts/resolve_tds_from_page.py --apply --only bradford
    python scripts/resolve_tds_from_page.py --apply --no-llm

Then:
    python scripts/ingest_tds_inbox.py --apply
    python scripts/validate_research_accuracy.py --resume --retry-failed
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ingest_tds_inbox as inbox
import sync_tds_library as library_mod
import tds_research_agent as tra

INBOX = ROOT / "data" / "tds_inbox"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

DOC_LINK = re.compile(r"""href=["']([^"']+\.(?:pdf|docx?)(?:\?[^"']*)?)["']""", re.I)

# Links that are never a product datasheet, however they are named.
EXCLUDE = re.compile(
    r"(privacy|terms|warranty|catalogue|catalog|price|order[-_]?form|"
    r"newsletter|careers|annual[-_]?report|installation[-_]?guide)", re.I)

IDENTIFY_SYSTEM = (
    "You identify which insulation product a technical datasheet describes. "
    "You answer with one number and nothing else."
)


def fetch_html(url: str, timeout: float) -> str | None:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, "ignore")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        print(f"    ! page fetch failed: {exc}", file=sys.stderr)
        return None


def document_links(html: str, base_url: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for raw in DOC_LINK.findall(html):
        absolute = urllib.parse.urljoin(base_url, raw)
        if EXCLUDE.search(absolute):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        found.append(absolute)
    return found


def ask_local_model(family_name: str, candidates: list[tuple[str, str]],
                    model: str, timeout: float) -> int | None:
    """Return the index of the candidate the local model believes matches, or
    None. Candidates are (url, text) pairs."""
    listing = "\n\n".join(
        f"[{i}] {url.rsplit('/', 1)[-1]}\n{text[:1200]}"
        for i, (url, text) in enumerate(candidates)
    )
    prompt = (
        f"Which of these datasheets describes the product \"{family_name}\"?\n\n"
        f"{listing}\n\n"
        f"Answer with the single number in brackets for the best match, or -1 "
        f"if none of them describe that product. Answer with the number only."
    )
    reply = _chat(model, IDENTIFY_SYSTEM, prompt, timeout)
    if not reply:
        return None
    match = re.search(r"-?\d+", reply)
    if not match:
        return None
    index = int(match.group(0))
    return index if 0 <= index < len(candidates) else None


def _chat(model: str, system: str, user: str, timeout: float) -> str | None:
    import llm_client
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "stream": False, "think": False, "keep_alive": "20m",
        "options": {"temperature": 0, "num_predict": 16, "num_ctx": 8192},
    }
    request = urllib.request.Request(
        f"{llm_client.OLLAMA_HOST}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        print(f"    ! local model call failed: {exc}", file=sys.stderr)
        return None
    return (data.get("message") or {}).get("content", "").strip() or None


def choose(family: dict, links: list[str], model: str | None,
           timeout: float) -> tuple[str | None, str]:
    """Pick the document on this page that belongs to the family."""
    if not links:
        return None, "page links no documents"
    if len(links) == 1:
        return links[0], "only document on the page"

    target = inbox.normalise(family["family_name"] or family["slug"])
    scored = sorted(
        ((inbox.score(inbox.normalise(url.rsplit("/", 1)[-1]), family), url) for url in links),
        key=lambda x: -x[0])
    best, best_url = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    if best >= 0.62 and best - runner_up >= 0.05:
        return best_url, f"filename match {best:.2f}"

    if not model:
        return None, f"{len(links)} documents, none clearly named (no-llm)"

    # Opaque filenames are common (Foilboard serves c33776_45165f83....pdf), so
    # fall back to reading the documents. Capped: downloading every PDF on a
    # large page to identify one is not a good trade.
    candidates: list[tuple[str, str]] = []
    for url in links[:6]:
        cached = tra.fetch_pdf(url)
        if cached is None:
            continue
        text = ""
        try:
            text = tra.pdf_text(cached, max_pages=2) or ""
        except Exception:  # noqa: BLE001
            pass
        if len(text) >= 200:
            candidates.append((url, text))
    if not candidates:
        return None, f"{len(links)} documents, none readable"

    index = ask_local_model(family["family_name"] or family["slug"],
                            candidates, model, timeout)
    if index is None:
        return None, f"{len(candidates)} documents, local model could not identify"
    return candidates[index][0], "identified by local model"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="download (default is a dry run)")
    parser.add_argument("--only", help="one manufacturer directory name")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--no-llm", action="store_true",
                        help="skip local-model identification; filename matching only")
    parser.add_argument("--model", default="llama3.2:latest",
                        help="local model for identification; a small one is enough")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--library", type=Path, default=library_mod.DEFAULT_LIBRARY)
    args = parser.parse_args()

    families = [f for f in inbox.load_families() if not f["has_source"]]
    targets = []
    for family in families:
        if args.only and family["manufacturer"].casefold() != args.only.casefold():
            continue
        data = family["data"]
        url = data.get("datasheet_download_url") or data.get("datasheet_pdf_url")
        if not url:
            continue
        if re.search(r"\.(pdf|docx?)(\?|$)", url.casefold()):
            continue  # a direct document; backfill handles those
        family["page_url"] = url
        targets.append(family)

    if args.limit:
        targets = targets[:args.limit]

    model = None if args.no_llm else args.model
    print(f"{len(targets)} family page(s) to resolve"
          f"{'' if model else ' (filename matching only)'}\n")

    resolved = 0
    reasons: dict[str, int] = {}
    staged: list[str] = []

    for family in targets:
        print(f"  {family['family_id']}\n    {family['page_url']}")
        html = fetch_html(family["page_url"], args.timeout)
        if html is None:
            reasons["page fetch failed"] = reasons.get("page fetch failed", 0) + 1
            continue

        links = document_links(html, family["page_url"])
        url, reason = choose(family, links, model, args.timeout)
        if url is None:
            print(f"    -> unresolved: {reason}")
            reasons[reason.split(",")[0]] = reasons.get(reason.split(",")[0], 0) + 1
            continue

        print(f"    -> {url.rsplit('/', 1)[-1][:70]}  ({reason})")
        resolved += 1
        staged.append(family["family_id"])

        if not args.apply:
            continue

        cached = tra.fetch_pdf(url)
        if cached is None:
            print("    ! download failed")
            resolved -= 1
            staged.pop()
            reasons["download failed"] = reasons.get("download failed", 0) + 1
            continue

        suffix = ".docx" if url.casefold().split("?")[0].endswith(".docx") else ".pdf"
        dest_dir = INBOX / family["manufacturer"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / f"{family['slug']}{suffix}").write_bytes(cached.read_bytes())

        data = family["data"]
        data["datasheet_pdf_url"] = url
        data["datasheet_page_url"] = family["page_url"]
        data["datasheet_source"] = "resolved_from_product_page"
        family["research_path"].write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        time.sleep(args.delay)

    print(f"\nresolved {resolved} of {len(targets)}"
          f"{'' if args.apply else '  (DRY RUN - re-run with --apply to download)'}")
    if reasons:
        print("unresolved reasons:")
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"  {count:>4}  {reason}")
    if args.apply and resolved:
        print("\nNext: python scripts/ingest_tds_inbox.py --apply")
        print("Then: python scripts/sync_tds_library.py --apply")


if __name__ == "__main__":
    main()
