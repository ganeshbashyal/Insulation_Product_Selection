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


def extract_text(content: bytes, content_type: str, url: str) -> str:
    if "pdf" in content_type.casefold() or urlparse(url).path.casefold().endswith(".pdf"):
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
    parser = TextExtractor()
    parser.feed(content.decode("utf-8", errors="replace"))
    return "\n".join(parser.parts)


def candidate_lines(text: str) -> list[str]:
    pattern = re.compile(r"\b(Rw|NRC|αw|alpha w|R[- ]?value|AS/NZS|temperature|fire|vapour|permeance)\b", re.I)
    return [line.strip() for line in text.splitlines() if pattern.search(line)][:200]


def ingest(family_id: str, url: str, output_dir: Path) -> Path:
    request = Request(url, headers={"User-Agent": "InsulationEvidencePOC/1.0"})
    with urlopen(request, timeout=45) as response:
        content = response.read()
        content_type = response.headers.get_content_type()
    checksum = hashlib.sha256(content).hexdigest()
    text = extract_text(content, content_type, url)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record = {
        "family_id": family_id,
        "source_url": url,
        "retrieved_at": timestamp,
        "sha256": checksum,
        "content_type": content_type,
        "review_status": "pending_human_review",
        "candidate_lines": candidate_lines(text),
        "review_instructions": "Compare each candidate with the source page/report. Add only approved claims to knowledge/performance_evidence.json with scope, variant, standard and test context.",
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
    args = parser.parse_args()
    print(ingest(args.family_id, args.url, args.output_dir))


if __name__ == "__main__":
    main()
