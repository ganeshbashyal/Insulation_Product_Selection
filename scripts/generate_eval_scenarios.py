"""Generate a realistic customer-enquiry scenario set for scripts/eval_scenarios.py.

Delegates the creative drafting (varied, plausible Australian customer wording)
to a local Ollama chat model -- no cloud API, no network call other than to
127.0.0.1. The deterministic ranker is never involved in generation, only in
the later scoring pass, so this cannot bias the eval toward the code under test.

Usage:
    python scripts/generate_eval_scenarios.py
    python scripts/generate_eval_scenarios.py --model llama3.1:8b --per-section 12
    python scripts/generate_eval_scenarios.py --out data/local/eval_scenarios_generated.txt
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.getenv("OLLAMA_SCENARIO_MODEL", "llama3.1:8b")

# Section headings match the A-H convention scripts/eval_scenarios.py parses.
SECTIONS = [
    ("A", "Ceiling and roof space insulation enquiries",
     "a homeowner or builder asking about insulating a ceiling, roof space, "
     "metal roof or attic in an Australian home"),
    ("B", "Wall insulation enquiries",
     "a homeowner, renovator or builder asking about insulating internal or "
     "external stud walls, including acoustic/soundproofing between rooms"),
    ("C", "Underfloor and subfloor insulation enquiries",
     "someone asking about insulating a suspended timber floor, subfloor or "
     "the space between two storeys"),
    ("D", "Pipe and duct lagging enquiries",
     "someone asking about insulating hot/cold water pipes, hydronic pipework "
     "or air-conditioning ductwork"),
    ("E", "Pricing, quoting and stock availability (should be handed off, not recommended)",
     "a customer asking purely about price, a quote, unit cost, or whether an "
     "item is currently in stock -- no product-fit question is being asked"),
    ("F", "Freight, delivery and order tracking (should be handed off, not recommended)",
     "a customer asking about delivery cost, freight, pickup, lead time, or "
     "tracking an order they already placed"),
    ("G", "Compliance and technical escalation (should be handed off, not recommended)",
     "a customer, certifier or specifier asking for a formal NCC/BAL/AS "
     "compliance sign-off, engineering certification, or a bushfire-attack-"
     "level determination that only a human specialist can approve"),
    ("H", "Ambiguous or out-of-scope enquiries (should be handed off, not recommended)",
     "a vague, multi-part, or entirely unrelated question that gives the "
     "assistant nothing concrete to match a product against"),
]

SYSTEM_PROMPT = (
    "You write short, realistic customer questions for an Australian "
    "insulation supplier's chat assistant. Each question must read like a "
    "real customer typed it: plain language, occasional typos or shorthand "
    "are fine, no marketing tone. Return ONLY the questions, one per line, "
    "each ending in a question mark. No numbering, no headings, no extra text."
)


def _ollama_chat(model: str, system_prompt: str, user_prompt: str, timeout: float) -> str | None:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "think": False,
        "keep_alive": "10m",
        "options": {"temperature": 0.8, "num_predict": 900, "num_ctx": 2048},
    }
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        print(f"  ! ollama call failed: {exc}", file=sys.stderr)
        return None
    return (data.get("message") or {}).get("content", "").strip() or None


def ollama_available() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def generate_section(model: str, label: str, brief: str, count: int, timeout: float) -> list[str]:
    prompt = (
        f"Write {count} different questions from {brief}. "
        "Vary the wording, the building type (house, shed, unit, renovation), "
        "and how technical or casual the customer sounds. "
        f"Each line must be a single question ending in '?'."
    )
    reply = _ollama_chat(model, SYSTEM_PROMPT, prompt, timeout)
    if not reply:
        return []
    lines = []
    for line in reply.splitlines():
        line = line.strip().lstrip("-*0123456789. ").strip()
        if line.endswith("?") and len(line) > 8:
            lines.append(line)
    return lines[:count]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama chat model to use for drafting")
    parser.add_argument("--per-section", type=int, default=15, help="questions to request per section")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--out", default=str(ROOT / "data" / "local" / "eval_scenarios_generated.txt"))
    args = parser.parse_args()

    if not ollama_available():
        print(
            "Local Ollama is not reachable at "
            f"{OLLAMA_HOST}. Start it with `ollama serve` and ensure "
            f"`{args.model}` is pulled, then re-run this script.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    out_lines = [
        f"{len(SECTIONS) * args.per_section} generated customer-enquiry scenarios "
        f"(drafted locally by {args.model} via Ollama; scored deterministically).",
        "",
    ]
    total = 0
    for code, label, brief in SECTIONS:
        print(f"[{code}] generating ~{args.per_section} scenarios: {label}")
        questions = generate_section(args.model, label, brief, args.per_section, args.timeout)
        print(f"    got {len(questions)} usable questions")
        out_lines.append(f"{code}. {label}")
        out_lines.extend(questions)
        out_lines.append("")
        total += len(questions)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"\nwrote {total} scenarios across {len(SECTIONS)} sections to {out_path}")


if __name__ == "__main__":
    main()
