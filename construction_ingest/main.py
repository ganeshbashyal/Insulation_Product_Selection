"""Unified local pipeline runner for the Australian construction data engine.

Wires the three layers into one query path with no cloud dependency:

    postcode -> climate zone -> phase/framing rules -> matching local products

Usage
-----
    python -m construction_ingest.main --build
    python -m construction_ingest.main --query "steel framed house in postcode 3000"
    python -m construction_ingest.main --postcode 3000 --framing steel --phase wrapping
    python -m construction_ingest.main --demo
    python -m construction_ingest.main --query "..." --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from construction_ingest import construction_matrix as matrix
from construction_ingest import db_setup
from construction_ingest.construction_matrix import FramingType, Phase
from construction_ingest.local_pdf_parser import (
    DEFAULT_OUTPUT as PRODUCT_KNOWLEDGE_PATH,
    DEFAULT_PDF_DIR,
    ProductRecord,
    load_product_knowledge,
    parse_directory,
)

SCOPE_NOTE = (
    "Screening aid only, generated locally. Not a compliance certificate. Confirm "
    "the climate zone on the ABCB Climate Map, and confirm required Total R-values "
    "with the project energy assessment and the building certifier."
)

PHASE_KEYWORDS: tuple[tuple[Phase, tuple[str, ...]], ...] = (
    (Phase.SLAB, ("slab", "subfloor", "footing", "dpm", "damp proof", "underfloor")),
    (Phase.FRAMING, ("framing", "frame", "stud", "thermal break")),
    (Phase.WRAPPING, ("wrap", "sarking", "membrane", "vapour", "vapor", "breather", "permeance")),
    (Phase.INSULATION, ("insulation", "batt", "batts", "cavity", "r-value", "r value", "ceiling")),
    (Phase.LINING, ("lining", "plasterboard", "gyprock", "board", "internal")),
)


@dataclass(slots=True)
class Query:
    """A parsed natural-language or flag-driven pipeline query."""

    postcode: str | None = None
    suburb: str | None = None
    framing: FramingType | None = None
    phases: list[Phase] = field(default_factory=list)
    raw: str = ""


def parse_query(text: str) -> Query:
    """Extract postcode, framing type and phases from free text."""
    body = text or ""
    lowered = body.casefold()

    postcode = None
    match = re.search(r"\b(\d{4})\b", body)
    if match:
        postcode = db_setup.normalise_postcode(match.group(1))

    framing: FramingType | None = None
    if re.search(r"steel|metal frame|nash|light gauge", lowered):
        framing = FramingType.STEEL
    elif re.search(r"timber|wood|stick.?built|as ?1684", lowered):
        framing = FramingType.TIMBER

    phases = [phase for phase, words in PHASE_KEYWORDS if any(word in lowered for word in words)]

    suburb = None
    suburb_match = re.search(r"\bin\s+([A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+)?)", body)
    if suburb_match and not suburb_match.group(1).casefold().startswith("postcode"):
        suburb = suburb_match.group(1)

    return Query(postcode=postcode, suburb=suburb, framing=framing, phases=phases, raw=body)


# ---------------------------------------------------------------------------
# Product matching
# ---------------------------------------------------------------------------


def match_products(
    products: list[ProductRecord],
    climate_zone: int | None,
    framing: FramingType | None,
    phases: list[Phase],
) -> list[dict]:
    """Screen locally extracted TDS products against the zone and framing.

    Returns candidates with an explicit reason, and never claims compliance -
    a product that fails the zone permeance threshold is returned flagged, not
    silently dropped, so the reason is visible.
    """
    if not products:
        return []

    requirement = matrix.membrane_requirement(climate_zone) if climate_zone else None
    minimum = requirement["minimum_vapour_permeance_ug_per_Ns"] if requirement else None
    membrane_phase = not phases or Phase.WRAPPING in phases
    insulation_phase = not phases or Phase.INSULATION in phases

    membrane_materials = {"Breather membrane", "Vapour barrier", "Reflective foil", "Polyethylene wrap"}
    bulk_materials = {"Glasswool", "Rockwool", "Polyester", "PIR board", "PUR board", "EPS board", "XPS board"}

    results: list[dict] = []
    for product in products:
        is_membrane = product.material_type in membrane_materials
        is_bulk = product.material_type in bulk_materials
        if is_membrane and not membrane_phase:
            continue
        if is_bulk and not insulation_phase:
            continue
        if not is_membrane and not is_bulk:
            continue

        reasons: list[str] = []
        flags: list[str] = []

        if framing and product.framing_compatibility and framing.value not in product.framing_compatibility:
            flags.append(f"TDS does not list {framing.value} framing compatibility")
        elif framing and framing.value in product.framing_compatibility:
            reasons.append(f"TDS lists {framing.value} framing compatibility")

        if is_membrane and minimum is not None:
            measured = product.vapour_permeance_ug_per_Ns
            if measured is None:
                flags.append(
                    f"zone {climate_zone} needs at least {minimum} ug/N.s but the TDS "
                    "permeance was not extracted - verify on the current data sheet"
                )
            elif measured < minimum:
                flags.append(
                    f"extracted permeance {measured} ug/N.s is below the zone "
                    f"{climate_zone} minimum of {minimum} ug/N.s"
                )
            else:
                reasons.append(f"extracted permeance {measured} ug/N.s meets the zone {climate_zone} minimum")
            if requirement and product.vapour_permeance_class in requirement["membrane_classes"]:
                reasons.append(f"{product.vapour_permeance_class} is in scope for zone {climate_zone}")

        if is_bulk and product.declared_r_value:
            reasons.append(f"declared R-values: {', '.join(product.declared_r_value[:6])}")

        results.append(
            {
                "manufacturer": product.manufacturer,
                "product_name": product.product_name,
                "material_type": product.material_type,
                "declared_r_value": product.declared_r_value[:6],
                "vapour_permeance_class": product.vapour_permeance_class,
                "vapour_permeance_ug_per_Ns": product.vapour_permeance_ug_per_Ns,
                "framing_compatibility": product.framing_compatibility,
                "source_pdf": product.source_pdf,
                "reasons": reasons,
                "flags": flags,
                "screening_status": "flagged" if flags else "candidate",
            }
        )

    results.sort(key=lambda item: (bool(item["flags"]), -len(item["reasons"])))
    return results


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run_query(
    query: Query | str,
    db_path: Path | str = db_setup.DEFAULT_DB_PATH,
    product_knowledge: Path | str = PRODUCT_KNOWLEDGE_PATH,
) -> dict:
    """Answer one construction query entirely from local data."""
    parsed = parse_query(query) if isinstance(query, str) else query
    answer: dict = {
        "query": parsed.raw,
        "scope_note": SCOPE_NOTE,
        "warnings": [],
    }

    # --- location -> climate zone ---
    location = None
    if parsed.postcode:
        if not Path(db_path).is_file():
            answer["warnings"].append(
                f"climate-zone database not found at {db_path}. "
                "Run: python -m construction_ingest.main --build"
            )
        else:
            connection = db_setup.connect(db_path)
            try:
                location = db_setup.lookup_postcode(connection, parsed.postcode, parsed.suburb)
            finally:
                connection.close()
            if location is None:
                answer["warnings"].append(f"no climate-zone record for postcode {parsed.postcode}")
    else:
        answer["warnings"].append("no postcode found in the query - climate-zone rules were not applied")

    answer["location"] = location
    climate_zone = location["climate_zone"] if location else None
    if location and location.get("requires_confirmation"):
        answer["warnings"].append(location["confirmation_note"])

    # --- framing ---
    framing = parsed.framing
    if framing is None:
        answer["warnings"].append("framing type not stated - showing timber and steel differences")
    answer["framing"] = (
        matrix.FRAMING_PROFILES[framing].as_dict() if framing else matrix.framing_comparison()
    )

    # --- rules ---
    phases = parsed.phases or list(matrix.PHASE_ORDER)
    answer["phases_requested"] = [phase.value for phase in phases]
    answer["rules"] = [
        {
            "phase": phase.value,
            "rules": [
                rule.as_dict()
                for rule in matrix.rules_for(phase=phase, framing_type=framing, climate_zone=climate_zone)
            ],
        }
        for phase in phases
    ]

    if climate_zone:
        answer["membrane_requirement"] = matrix.membrane_requirement(climate_zone)

    # --- local product knowledge ---
    knowledge = load_product_knowledge(product_knowledge)
    if knowledge is None:
        answer["products"] = []
        answer["warnings"].append(
            f"no local product knowledge at {product_knowledge}. "
            f"Drop TDS PDFs into {DEFAULT_PDF_DIR} and run: "
            "python -m construction_ingest.local_pdf_parser"
        )
    else:
        answer["products"] = match_products(knowledge.products, climate_zone, framing, phases)
        answer["product_knowledge_generated_at"] = knowledge.generated_at

    return answer


def build_all(
    db_path: Path | str = db_setup.DEFAULT_DB_PATH,
    pdf_dir: Path | str = DEFAULT_PDF_DIR,
    offline: bool = False,
    use_llm: bool = True,
) -> dict:
    """Build every local artefact: SQLite zones, JSON map and product knowledge."""
    print("[1/3] Building postcode -> climate zone database")
    stats = db_setup.build_database(db_path=db_path, offline=offline)

    print("[2/3] Exporting JSON lookup map")
    connection = db_setup.connect(db_path)
    try:
        json_path = db_setup.export_json(connection)
    finally:
        connection.close()

    print("[3/3] Parsing local TDS PDFs")
    document = parse_directory(pdf_dir=pdf_dir, use_llm=use_llm)

    return {
        "database": str(db_path),
        "json_map": str(json_path),
        "postcodes": stats["distinct_postcodes"],
        "authoritative_rows": stats["authoritative_rows"],
        "products": len(document.products),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render(answer: dict) -> str:
    lines: list[str] = []
    if answer.get("query"):
        lines.append(f"Q: {answer['query']}")
        lines.append("=" * 78)

    location = answer.get("location")
    if location:
        suburb = f"{location['suburb']}, " if location["suburb"] else ""
        lines.append(
            f"Location : {suburb}{location['state']} {location['postcode']} "
            f"-> NCC climate zone {location['climate_zone']} ({location['zone_description']})"
        )
        lines.append(f"NCC      : {location['ncc_volume']}")
        lines.append(f"Source   : {location['source']} [{location['confidence']}]")
        if len(location["zones_in_postcode"]) > 1:
            zones = ", ".join(str(z) for z in location["zones_in_postcode"])
            lines.append(f"           note: this postcode spans zones {zones}")
    else:
        lines.append("Location : not resolved")

    framing = answer.get("framing") or {}
    if "framing_type" in framing:
        lines.append(
            f"Framing  : {framing['framing_type']} "
            f"({framing['thermal_conductivity_w_mk']} W/mK, "
            f"thermal break required: {'yes' if framing['thermal_break_required'] else 'no'})"
        )
    elif framing:
        lines.append(
            f"Framing  : not stated - steel conducts ~{framing['conductivity_ratio']}x more heat than timber"
        )

    membrane = answer.get("membrane_requirement")
    if membrane:
        minimum = membrane["minimum_vapour_permeance_ug_per_Ns"]
        threshold = f"at least {minimum} ug/N.s" if minimum else "no zone-specific minimum"
        lines.append(f"Membrane : {threshold} ({', '.join(membrane['membrane_classes'])})")

    for block in answer.get("rules", []):
        if not block["rules"]:
            continue
        lines.append("")
        lines.append(f"--- {block['phase']} " + "-" * max(0, 74 - len(block["phase"])))
        for rule in block["rules"]:
            marker = {"required": "[!]", "recommended": "[+]", "informational": "[i]"}.get(rule["severity"], "[ ]")
            lines.append(f"{marker} {rule['requirement']}")
            lines.append(f"    Material : {rule['material']}")
            lines.append(f"    Provision: {rule['provision']}")
            if rule["verification"]:
                lines.append(f"    Verify   : {rule['verification']}")

    products = answer.get("products") or []
    if products:
        lines.append("")
        lines.append("--- Local product candidates " + "-" * 49)
        for product in products[:10]:
            lines.append(f"[{product['screening_status']}] {product['manufacturer']} {product['product_name']}")
            for reason in product["reasons"]:
                lines.append(f"    + {reason}")
            for flag in product["flags"]:
                lines.append(f"    ! {flag}")

    warnings = answer.get("warnings") or []
    if warnings:
        lines.append("")
        lines.append("--- Notes " + "-" * 68)
        for warning in warnings:
            lines.append(f"  * {warning}")

    lines.append("")
    lines.append(answer["scope_note"])
    return "\n".join(lines)


DEMO_QUERIES = (
    "What wrap and insulation stage applies to a steel-framed house in postcode 3000 (Melbourne)?",
    "Timber framed house in postcode 4000 Brisbane - what wall wrap do I need?",
    "Steel frame in postcode 7000 Hobart, what thermal break and membrane apply?",
    "What goes in the slab stage for postcode 0800 Darwin?",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--build", action="store_true", help="build the database, JSON map and product knowledge")
    parser.add_argument("--offline", action="store_true", help="during --build, skip all downloads")
    parser.add_argument("--no-llm", action="store_true", help="during --build, skip Ollama and use regex extraction")
    parser.add_argument("--query", help="natural-language question")
    parser.add_argument("--postcode", help="4-digit postcode")
    parser.add_argument("--suburb", help="suburb name, to disambiguate a multi-zone postcode")
    parser.add_argument("--framing", choices=["timber", "steel"], help="framing type")
    parser.add_argument(
        "--phase",
        action="append",
        default=[],
        choices=["slab", "framing", "wrapping", "insulation", "lining"],
        help="restrict to a construction phase (repeatable)",
    )
    parser.add_argument("--db", default=str(db_setup.DEFAULT_DB_PATH), help="climate-zone database path")
    parser.add_argument("--demo", action="store_true", help="run the built-in demo queries")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of formatted text")
    args = parser.parse_args(argv)

    if args.build:
        stats = build_all(db_path=args.db, offline=args.offline, use_llm=not args.no_llm)
        print(json.dumps(stats, indent=2))
        if not (args.query or args.postcode or args.demo):
            return 0

    if args.demo:
        for text in DEMO_QUERIES:
            answer = run_query(text, db_path=args.db)
            print(json.dumps(answer, indent=2) if args.json else render(answer))
            print("\n")
        return 0

    if args.query:
        query = parse_query(args.query)
    elif args.postcode or args.framing or args.phase:
        query = Query(raw="(flags)")
    else:
        parser.print_help()
        return 1

    phase_lookup = {
        "slab": Phase.SLAB,
        "framing": Phase.FRAMING,
        "wrapping": Phase.WRAPPING,
        "insulation": Phase.INSULATION,
        "lining": Phase.LINING,
    }
    if args.postcode:
        query.postcode = db_setup.normalise_postcode(args.postcode)
    if args.suburb:
        query.suburb = args.suburb
    if args.framing:
        query.framing = matrix.coerce_framing(args.framing)
    if args.phase:
        query.phases = [phase_lookup[name] for name in args.phase]

    if query.postcode is None and args.postcode:
        print(f"Not a valid Australian postcode: {args.postcode}", file=sys.stderr)
        return 1

    answer = run_query(query, db_path=args.db)
    print(json.dumps(answer, indent=2) if args.json else render(answer))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
