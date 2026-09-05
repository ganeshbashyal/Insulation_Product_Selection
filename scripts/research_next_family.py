"""Process exactly one un-researched family through the TDS deep-dive agent.

Designed to run repeatedly in the background, one family per invocation, so it
stays reliable on a local LLM and can be scheduled (Task Scheduler / cron) or
run in a loop without overloading the machine. Each run:
  1. finds the first family with no successful research JSON yet
  2. resolves its datasheet PDF (SKU catalogue -> official source_url -> web search)
  3. downloads and extracts it with the local Ollama model
  4. writes knowledge/<mfg>/research/<slug>.json
  5. regenerates that family's MD + DOCX literature

Run it once:
    python scripts/research_next_family.py

Loop until done (your call — each pass handles one family):
    python scripts/research_next_family.py --loop --delay 3

Check progress:
    python scripts/research_next_family.py --status
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import tds_research_agent as agent
from generate_family_literature import main as _lit_main  # noqa: F401  (import for side-effect-free reuse)


# Statuses that mean "we tried and there is nothing more to do automatically".
# These families are skipped on later runs until you supply a link (via the TDS
# CSV) or one becomes discoverable; re-run tds_research_agent.py --only <mfg>
# after filling links to force a retry.
TERMINAL_STATUSES = {"ok", "no_pdf_found", "fetch_failed", "no_text"}


def pending_families() -> list[tuple[str, dict]]:
    """Families not yet successfully researched AND not at a terminal dead-end."""
    pending = []
    for path in sorted(ROOT.glob("knowledge/*/families.json")):
        manufacturer_dir = path.parent.name
        data = json.loads(path.read_text(encoding="utf-8"))
        for family in data["families"]:
            family.setdefault("manufacturer", manufacturer_dir.title())
            slug = agent.slugify(family["name"])
            research_file = agent.research_path(manufacturer_dir, slug)
            status = None
            if research_file.exists():
                try:
                    status = json.loads(research_file.read_text(encoding="utf-8")).get("status")
                except (json.JSONDecodeError, OSError):
                    status = None
            if status not in TERMINAL_STATUSES:
                pending.append((manufacturer_dir, family))
    return pending


def process_one() -> str | None:
    pending = pending_families()
    if not pending:
        return None
    manufacturer_dir, family = pending[0]
    slug = agent.slugify(family["name"])
    print(f"researching: {manufacturer_dir} / {family['name']}")
    result = agent.process_family(manufacturer_dir, family, delay=0.5)
    print(f"  -> {result}")
    if result == "ok":
        # regenerate just this manufacturer's literature so the rich data lands
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "generate_family_literature.py"), "--only", manufacturer_dir],
            cwd=ROOT, check=False, capture_output=True,
        )
        print("  -> literature regenerated")
    return result


def status() -> None:
    agent.status_report()
    remaining = len(pending_families())
    print(f"pending families: {remaining}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="keep processing until none remain")
    parser.add_argument("--delay", type=float, default=3.0, help="seconds between families in --loop")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.status:
        status()
        return

    if args.loop:
        while True:
            result = process_one()
            if result is None:
                print("all families researched.")
                break
            time.sleep(args.delay)
    else:
        if process_one() is None:
            print("all families researched.")


if __name__ == "__main__":
    main()
