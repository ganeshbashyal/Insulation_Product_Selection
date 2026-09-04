"""Download a TDS/PDS source into a human-review inbox; never auto-publish claims."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if value:
            self.parts.append(value)


def extract_candidates(content: bytes, content_type: str, url: str) -> tuple[list[dict], bool]:
    pattern = re.compile(r"\b(Rw|NRC|αw|alpha w|R[- ]?value|AS/NZS|temperature|fire|vapour|permeance)\b", re.I)
    if "pdf" in content_type.casefold() or urlparse(url).path.casefold().endswith(".pdf"):
        from pypdf import PdfReader
        candidates = []
        pages_with_text = 0
        pages = PdfReader(BytesIO(content)).pages
        for page_number, page in enumerate(pages, start=1):
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages_with_text += 1
            for line in page_text.splitlines():
                if pattern.search(line):
                    candidates.append({"text": line.strip(), "page": page_number, "region": "text line; coordinates unavailable", "extractor_confidence": 0.75, "ocr_confidence": None})
        return candidates[:200], bool(pages) and pages_with_text == 0
    parser = TextExtractor()
    parser.feed(content.decode("utf-8", errors="replace"))
    candidates = [{"text": line, "page": None, "region": "HTML text block", "extractor_confidence": 0.8, "ocr_confidence": None} for line in parser.parts if pattern.search(line)]
    return candidates[:200], False


def ingest(family_id: str, url: str, output_dir: Path, raw_dir: Path) -> Path:
    request = Request(url, headers={"User-Agent": "InsulationEvidencePOC/1.0"})
    with urlopen(request, timeout=45) as response:
        content = response.read()
        content_type = response.headers.get_content_type()
    checksum = hashlib.sha256(content).hexdigest()
    candidates, ocr_required = extract_candidates(content, content_type, url)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    suffix = ".pdf" if "pdf" in content_type.casefold() or urlparse(url).path.casefold().endswith(".pdf") else ".html"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{checksum}{suffix}"
    if not raw_path.exists():
        raw_path.write_bytes(content)
    record = {
        "family_id": family_id,
        "source_url": url,
        "retrieved_at": timestamp,
        "sha256": checksum,
        "content_type": content_type,
        "review_status": "pending_human_review",
        "raw_binary": str(raw_path.relative_to(ROOT)).replace("\\", "/"),
        "ocr_required": ocr_required,
        "auto_promotion_allowed": False,
        "candidates": candidates,
        "review_instructions": "Compare each candidate with the hashed raw source. Record page/region, scope, variant and standard. Only an authorised human may add verified_by and verified_at and promote a claim.",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{family_id.casefold()}-{checksum[:10]}.json"
    destination.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family-id", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evidence" / "inbox")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "evidence" / "raw")
    args = parser.parse_args()
    print(ingest(args.family_id, args.url, args.output_dir, args.raw_dir))


if __name__ == "__main__":
    main()
