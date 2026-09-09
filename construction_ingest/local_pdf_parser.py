"""Local PDF technical data sheet ingestion via Ollama.

Extracts text from TDS PDFs on disk and asks a *local* Ollama model to return
structured JSON validated by Pydantic. Nothing leaves the machine: the only
network call is to ``OLLAMA_HOST`` (default ``http://127.0.0.1:11434``).

Usage
-----
    python -m construction_ingest.local_pdf_parser --pdf-dir data/tds
    python -m construction_ingest.local_pdf_parser --pdf-dir data/tds --model mistral
    python -m construction_ingest.local_pdf_parser --pdf-dir data/tds --no-llm

``--no-llm`` runs the regex pre-extraction only, so the pipeline still produces
a (lower-confidence) record set when Ollama is not running.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF_DIR = ROOT / "data" / "tds"
DEFAULT_OUTPUT = ROOT / "data" / "product_knowledge.json"

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_TDS_MODEL", os.getenv("OLLAMA_MODEL", "llama3.2"))
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))

#: Text beyond this is dropped before prompting - a TDS states its key
#: attributes early, and an oversized prompt is slow and degrades extraction.
MAX_CHARS_PER_PROMPT = 12000

KNOWN_MANUFACTURERS = (
    "CSR Bradford", "Bradford", "Kingspan", "Ametalin", "Knauf", "Fletcher",
    "Fletcher Insulation", "Autex", "Aircell", "Acoustica", "Ecowool",
    "Polyester Solutions", "Higgins", "Proctor", "Thermotec", "Sisalation",
    "Earthwool", "Pink Batts", "James Hardie", "Siniat", "Gyprock", "USG Boral",
)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

MaterialType = Literal[
    "Glasswool", "Rockwool", "Polyester", "PIR board", "PUR board", "EPS board",
    "XPS board", "Polyethylene wrap", "Reflective foil", "Breather membrane",
    "Vapour barrier", "Tape", "Accessory", "Plasterboard", "Unknown",
]

VapourClass = Literal["Class 1", "Class 2", "Class 3", "Class 4", "Not stated"]

Framing = Literal["Timber", "Steel"]


class ProductRecord(BaseModel):
    """One product extracted from a technical data sheet."""

    manufacturer: str = Field(default="Unknown", description="e.g. CSR Bradford, Kingspan, Ametalin, Knauf")
    product_name: str = Field(default="Unknown")
    material_type: MaterialType = "Unknown"
    declared_r_value: list[str] = Field(
        default_factory=list, description="Declared R-values as printed, e.g. ['R2.5', 'R4.0']"
    )
    vapour_permeance_class: VapourClass = "Not stated"
    vapour_permeance_ug_per_Ns: float | None = Field(
        default=None, description="Measured vapour permeance in ug/N.s if the TDS states it"
    )
    framing_compatibility: list[Framing] = Field(default_factory=list)
    ncc_compliance_notes: str = ""
    standards_cited: list[str] = Field(default_factory=list)
    source_pdf: str = ""
    extracted_at: str = ""
    extraction_method: Literal["ollama", "regex", "ollama+regex"] = "regex"
    extraction_warnings: list[str] = Field(default_factory=list)

    @field_validator("declared_r_value", mode="before")
    @classmethod
    def _coerce_r_values(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (str, int, float)):
            value = [value]
        if not isinstance(value, (list, tuple, set)):
            return []
        seen: list[str] = []
        for item in value:
            match = re.search(r"(\d+(?:\.\d+)?)", str(item))
            if not match:
                continue
            text = f"R{float(match.group(1)):g}"
            if text not in seen:
                seen.append(text)
        return seen

    @field_validator("framing_compatibility", mode="before")
    @classmethod
    def _coerce_framing(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple, set)):
            return []
        result: list[str] = []
        for item in value:
            text = str(item).casefold()
            if ("steel" in text or "metal" in text) and "Steel" not in result:
                result.append("Steel")
            if ("timber" in text or "wood" in text) and "Timber" not in result:
                result.append("Timber")
        return result

    @field_validator("vapour_permeance_class", mode="before")
    @classmethod
    def _coerce_vapour_class(cls, value: object) -> str:
        if value is None:
            return "Not stated"
        match = re.search(r"[1-4]", str(value))
        return f"Class {match.group(0)}" if match else "Not stated"

    @field_validator("material_type", mode="before")
    @classmethod
    def _coerce_material(cls, value: object) -> str:
        if value is None:
            return "Unknown"
        text = str(value).casefold()
        aliases: tuple[tuple[str, str], ...] = (
            ("glass wool", "Glasswool"), ("glasswool", "Glasswool"), ("fibreglass", "Glasswool"),
            ("fiberglass", "Glasswool"), ("mineral wool", "Rockwool"), ("rock wool", "Rockwool"),
            ("rockwool", "Rockwool"), ("stone wool", "Rockwool"), ("polyester", "Polyester"),
            ("pir", "PIR board"), ("polyisocyanurate", "PIR board"), ("polyurethane", "PUR board"),
            ("pur", "PUR board"), ("expanded polystyrene", "EPS board"), ("eps", "EPS board"),
            ("extruded polystyrene", "XPS board"), ("xps", "XPS board"),
            ("polyethylene", "Polyethylene wrap"), ("breather", "Breather membrane"),
            ("vapour permeable", "Breather membrane"), ("vapour barrier", "Vapour barrier"),
            ("reflective foil", "Reflective foil"), ("foil", "Reflective foil"),
            ("sarking", "Reflective foil"), ("tape", "Tape"),
            ("plasterboard", "Plasterboard"), ("gyprock", "Plasterboard"),
        )
        for needle, canonical in aliases:
            if needle in text:
                return canonical
        return "Unknown"


class ProductKnowledge(BaseModel):
    """The full output document written to ``product_knowledge.json``."""

    generated_at: str
    model: str
    source_directory: str
    pdf_count: int
    products: list[ProductRecord]
    scope_note: str = (
        "Extracted from manufacturer technical data sheets by a local model. "
        "Values must be verified against the current TDS before selection or quoting. "
        "This is not evidence of NCC compliance."
    )


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------


def extract_pdf_text(path: Path, max_pages: int = 12) -> str:
    """Extract text from a PDF using pdfplumber, falling back to pypdf."""
    try:
        import pdfplumber  # noqa: PLC0415 - optional dependency

        with pdfplumber.open(path) as pdf:
            pages = [(page.extract_text() or "") for page in pdf.pages[:max_pages]]
        text = "\n".join(pages).strip()
        if text:
            return text
    except ImportError:
        pass
    except Exception as error:  # noqa: BLE001 - a malformed PDF must not stop the batch
        print(f"  ! pdfplumber failed on {path.name}: {type(error).__name__}", file=sys.stderr)

    try:
        from pypdf import PdfReader  # noqa: PLC0415 - optional dependency

        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:max_pages]).strip()
    except ImportError:
        print("  ! neither pdfplumber nor pypdf is installed", file=sys.stderr)
    except Exception as error:  # noqa: BLE001
        print(f"  ! pypdf failed on {path.name}: {type(error).__name__}", file=sys.stderr)
    return ""


def iter_pdfs(directory: Path) -> Iterator[Path]:
    yield from sorted(p for p in directory.rglob("*.pdf") if p.is_file())


# ---------------------------------------------------------------------------
# Deterministic pre-extraction
# ---------------------------------------------------------------------------


def regex_prefill(text: str, source_name: str) -> dict:
    """Pull the high-confidence, unambiguous fields without the model.

    These are cheap, deterministic and used both as a fallback when Ollama is
    unavailable and as a cross-check on the model's output.
    """
    body = text or ""
    lowered = body.casefold()

    manufacturer = next((m for m in KNOWN_MANUFACTURERS if m.casefold() in lowered), "Unknown")

    r_values = [f"R{float(v):g}" for v in re.findall(r"\bR\s?(\d+(?:\.\d+)?)\b", body)]
    r_values = list(dict.fromkeys(r_values))[:24]

    vapour_class = "Not stated"
    class_match = re.search(r"\bclass\s*([1-4])\b", lowered)
    if class_match:
        vapour_class = f"Class {class_match.group(1)}"

    permeance: float | None = None
    permeance_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:ug|µg|μg)\s*/?\s*n\.?\s*s",
        lowered.replace(" per ", "/"),
    )
    if permeance_match:
        try:
            permeance = float(permeance_match.group(1))
        except ValueError:
            permeance = None

    framing: list[str] = []
    if re.search(r"steel|metal frame", lowered):
        framing.append("Steel")
    if re.search(r"timber|wood frame", lowered):
        framing.append("Timber")

    standards = sorted({
        re.sub(r"\s+", " ", match.group(0)).upper()
        for match in re.finditer(r"AS(?:/NZS)?\s?\d{3,4}(?:\.\d+)?", body)
    })

    return {
        "manufacturer": manufacturer,
        "product_name": _guess_product_name(body, source_name),
        "declared_r_value": r_values,
        "vapour_permeance_class": vapour_class,
        "vapour_permeance_ug_per_Ns": permeance,
        "framing_compatibility": framing,
        "standards_cited": standards[:12],
        "material_type": body[:600],  # validator maps free text to a canonical type
    }


def _guess_product_name(text: str, source_name: str) -> str:
    for line in (text or "").splitlines():
        candidate = line.strip()
        if 3 < len(candidate) <= 80 and not candidate.casefold().startswith(("page ", "www.", "http")):
            return candidate
    return Path(source_name).stem.replace("_", " ").replace("-", " ").title()


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """You extract structured facts from Australian insulation and building membrane technical data sheets.

Return ONLY a JSON object. No prose, no markdown fences, no explanation.

Rules:
- Only report what the document actually states. Never infer, estimate or complete a value from general knowledge.
- If a field is not stated in the document, use null for scalars and [] for lists.
- Do not assert NCC compliance. Record only compliance statements the document itself makes, quoted or closely paraphrased.

Schema:
{
  "manufacturer": string|null,
  "product_name": string|null,
  "material_type": one of ["Glasswool","Rockwool","Polyester","PIR board","PUR board","EPS board","XPS board","Polyethylene wrap","Reflective foil","Breather membrane","Vapour barrier","Tape","Accessory","Plasterboard","Unknown"],
  "declared_r_value": [string],
  "vapour_permeance_class": one of ["Class 1","Class 2","Class 3","Class 4","Not stated"],
  "vapour_permeance_ug_per_Ns": number|null,
  "framing_compatibility": subset of ["Timber","Steel"],
  "ncc_compliance_notes": string,
  "standards_cited": [string]
}
"""


class OllamaUnavailable(RuntimeError):
    """The local Ollama server could not be reached or did not answer."""


def ollama_available(host: str = OLLAMA_HOST, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=timeout) as response:  # noqa: S310
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def call_ollama(
    prompt: str,
    model: str = OLLAMA_MODEL,
    host: str = OLLAMA_HOST,
    timeout: float = OLLAMA_TIMEOUT_SECONDS,
    retries: int = 2,
) -> dict:
    """Call ``/api/generate`` with ``format=json`` and return the parsed object."""
    payload = {
        "model": model,
        "prompt": prompt,
        "system": EXTRACTION_SYSTEM_PROMPT,
        "stream": False,
        "format": "json",
        "keep_alive": "30m",
        "options": {"temperature": 0.0, "num_predict": 900, "num_ctx": 8192},
    }
    request = urllib.request.Request(
        f"{host}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    last_error = "unknown error"
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            last_error = f"HTTP {error.code} from Ollama (is the '{model}' model pulled?)"
        except (TimeoutError, urllib.error.URLError) as error:
            last_error = f"cannot reach Ollama at {host} ({type(error).__name__})"
        except (OSError, json.JSONDecodeError) as error:
            last_error = f"bad response from Ollama ({type(error).__name__})"
        else:
            parsed = _parse_model_json(body.get("response", ""))
            if parsed is not None:
                return parsed
            last_error = "model did not return valid JSON"
        if attempt < retries:
            print(f"  . retry {attempt}/{retries - 1}: {last_error}", file=sys.stderr)
    raise OllamaUnavailable(last_error)


def _parse_model_json(text: str) -> dict | None:
    """Parse the model's reply, tolerating fences and surrounding prose."""
    content = (text or "").strip()
    if not content:
        return None
    content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            parsed = json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def parse_pdf(path: Path, model: str = OLLAMA_MODEL, use_llm: bool = True) -> ProductRecord:
    """Parse one TDS PDF into a validated ``ProductRecord``."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    text = extract_pdf_text(path)
    if not text:
        return ProductRecord(
            product_name=path.stem.replace("_", " ").title(),
            source_pdf=str(path),
            extracted_at=now,
            extraction_method="regex",
            extraction_warnings=["no extractable text - the PDF may be a scanned image"],
        )

    prefill = regex_prefill(text, path.name)
    warnings: list[str] = []
    method: str = "regex"
    data = dict(prefill)

    if use_llm:
        prompt = (
            f"Technical data sheet file name: {path.name}\n\n"
            f"Document text:\n{text[:MAX_CHARS_PER_PROMPT]}"
        )
        try:
            extracted = call_ollama(prompt, model=model)
        except OllamaUnavailable as error:
            warnings.append(f"ollama unavailable, regex fallback only: {error}")
        else:
            method = "ollama+regex"
            for key, value in extracted.items():
                if value in (None, "", [], {}):
                    continue
                data[key] = value
            # Regex-only signals the model has no reason to invent.
            if not data.get("standards_cited"):
                data["standards_cited"] = prefill["standards_cited"]
            if prefill["vapour_permeance_ug_per_Ns"] is not None and not extracted.get("vapour_permeance_ug_per_Ns"):
                data["vapour_permeance_ug_per_Ns"] = prefill["vapour_permeance_ug_per_Ns"]

    data.update(
        source_pdf=str(path),
        extracted_at=now,
        extraction_method=method,
        extraction_warnings=warnings,
    )
    try:
        return ProductRecord.model_validate(data)
    except ValidationError as error:
        return ProductRecord(
            product_name=path.stem.replace("_", " ").title(),
            source_pdf=str(path),
            extracted_at=now,
            extraction_method="regex",
            extraction_warnings=[f"validation failed: {error.error_count()} field error(s)"],
        )


def parse_directory(
    pdf_dir: Path | str = DEFAULT_PDF_DIR,
    output: Path | str = DEFAULT_OUTPUT,
    model: str = OLLAMA_MODEL,
    use_llm: bool = True,
) -> ProductKnowledge:
    """Parse every PDF in a directory tree and write ``product_knowledge.json``.

    Also writes a sibling ``<output>.status.json`` summary (counts by
    extraction method/outcome) so a caller - a human running this locally, or
    data_health.py - can check how the run went without re-parsing every PDF.
    """
    directory = Path(pdf_dir)
    directory.mkdir(parents=True, exist_ok=True)
    pdfs = list(iter_pdfs(directory))

    if use_llm and not ollama_available():
        print(
            f"  ! Ollama not reachable at {OLLAMA_HOST} - falling back to regex extraction.\n"
            f"    Start it with 'ollama serve' and pull a model with 'ollama pull {model}'.",
            file=sys.stderr,
        )
        use_llm = False

    records: list[ProductRecord] = []
    per_file_status: list[dict] = []
    for index, path in enumerate(pdfs, start=1):
        record = parse_pdf(path, model=model, use_llm=use_llm)
        records.append(record)
        if record.extraction_warnings:
            outcome = "warn"
        elif record.extraction_method == "ollama+regex":
            outcome = "ok"
        else:
            outcome = "ok-regex-only"
        print(f"  [{index}/{len(pdfs)}] {_status_tag(outcome)} {path.name} ({record.extraction_method})")
        for warning in record.extraction_warnings:
            print(f"        - {warning}")
        per_file_status.append({
            "file": path.name,
            "outcome": outcome,
            "extraction_method": record.extraction_method,
            "warnings": record.extraction_warnings,
        })

    document = ProductKnowledge(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model=model if use_llm else "regex-only",
        source_directory=str(directory),
        pdf_count=len(pdfs),
        products=records,
    )
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document.model_dump_json(indent=2), encoding="utf-8")

    ok_count = sum(1 for s in per_file_status if s["outcome"] == "ok")
    warn_count = sum(1 for s in per_file_status if s["outcome"] == "warn")
    regex_only_count = sum(1 for s in per_file_status if s["outcome"] == "ok-regex-only")
    status_summary = {
        "generated_at": document.generated_at,
        "pdf_dir": str(directory),
        "output": str(output_path),
        "used_llm": use_llm,
        "model": model if use_llm else "regex-only",
        "pdf_count": len(pdfs),
        "ok": ok_count,
        "regex_only": regex_only_count,
        "warnings": warn_count,
        "files": per_file_status,
    }
    status_path = output_path.with_name(output_path.stem + "_status.json")
    status_path.write_text(json.dumps(status_summary, indent=2), encoding="utf-8")
    print(
        f"\nSummary: {len(pdfs)} PDF(s) -> {ok_count} ok (llm), {regex_only_count} regex-only, "
        f"{warn_count} with warnings. Status written to {status_path}."
    )
    return document


def _status_tag(outcome: str) -> str:
    return {"ok": "[OK]", "ok-regex-only": "[REGEX]", "warn": "[WARN]"}.get(outcome, "[?]")


def load_product_knowledge(path: Path | str = DEFAULT_OUTPUT) -> ProductKnowledge | None:
    """Read a previously generated ``product_knowledge.json``."""
    file_path = Path(path)
    if not file_path.is_file():
        return None
    try:
        return ProductKnowledge.model_validate_json(file_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, json.JSONDecodeError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdf-dir", default=str(DEFAULT_PDF_DIR), help="folder of TDS PDFs (searched recursively)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="output JSON path")
    parser.add_argument("--model", default=OLLAMA_MODEL, help="local Ollama model, e.g. llama3.2 or mistral")
    parser.add_argument("--no-llm", action="store_true", help="regex extraction only, never call Ollama")
    args = parser.parse_args(argv)

    print(f"Parsing TDS PDFs in {args.pdf_dir} (model: {'regex-only' if args.no_llm else args.model})")
    document = parse_directory(
        pdf_dir=args.pdf_dir,
        output=args.output,
        model=args.model,
        use_llm=not args.no_llm,
    )
    if not document.pdf_count:
        print(f"  no PDFs found. Drop technical data sheets into {args.pdf_dir} and re-run.")
        return 1
    print(f"  wrote {len(document.products)} product record(s) to {args.output}")
    warning_count = sum(1 for record in document.products if record.extraction_warnings)
    if warning_count:
        print(f"  {warning_count}/{len(document.products)} record(s) had extraction warnings - see the status JSON for detail.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
