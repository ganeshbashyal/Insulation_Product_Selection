"""Ingest the master SKU workbook into the local catalogue database.

The workbook is the commercial source of truth: column ``sku`` is the identifier
used in MYOB and online, so it is the primary key here. Two properties of the
real data shape this script:

* ``sku`` is not unique and not always present. 18 active rows share a ``sku``
  (genuine pack/variant duplicates) and 31 have none. ``OURSKU`` is unique
  across active rows and is therefore the internal row key, with ``sku`` carried
  alongside and indexed for MYOB lookups.
* Superseded rows are retained in the sheet. 27 ``OURSKU`` values appear more
  than once, and in every case exactly one row is ``active? = yes``, so
  filtering to active rows both de-duplicates and drops discontinued lines.

Mapping a SKU to a knowledge-base family is deliberately conservative. Product
names alone produce confident nonsense - matching on the shared token "batt"
maps 92 Autex batts onto a panel accessory - so a family is only assigned when a
distinctive name token is corroborated by product use or material. Anything
weaker is written with ``match_tier = 'review'`` and a null ``family_id`` so it
is visible for human confirmation but cannot silently drive a recommendation.

Local-only: reads a local workbook, writes a local SQLite file, no network use.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
WORKBOOK = ROOT / "data" / "raw" / "Product_Master_Bot_KB_SKU_Matched_cleaned_remapped_auto_remapped.xlsx"
SHEET = "CLEANED"
DB_PATH = ROOT / "data" / "local" / "family_catalogue.sqlite3"
CARDS = ROOT / "data" / "processed" / "retrieval_cards.jsonl"
REVIEW_CSV = ROOT / "data" / "local" / "sku_family_review.csv"

# Tokens shared by most products in a category. They describe what a thing is,
# not which family it belongs to, so they must never carry a match on their own.
GENERIC_TOKENS = {
    "batt", "batts", "board", "panel", "roll", "rolls", "blanket", "wrap",
    "sarking", "insulation", "acoustic", "thermal", "wall", "walls", "ceiling",
    "floor", "pipe", "accessory", "internal", "external", "general",
    "commercial", "bulk", "reflective", "membrane", "foam", "rigid", "system",
    "systems", "kit", "tape",
}

# productuse value -> phrases that should appear in a matching family's text.
USE_TERMS = {
    "ceiling": ("ceiling", "roof"),
    "internalwall": ("internal wall", "partition", "interior wall"),
    "externalwall": ("external wall", "exterior wall", "facade", "cladding"),
    "underfloor": ("underfloor", "under floor", "subfloor", "floor"),
    "wallwrapsarking": ("wall wrap", "sarking", "membrane", "breather"),
    "pipe": ("pipe", "duct", "lagging"),
    "generalacoustic": ("acoustic", "sound", "noise"),
}

# Broad product forms. A SKU may only be auto-linked to a family of the same
# form: an accessory must not be sold as the product it accompanies, and a mesh
# must not be linked to a tape. Anything unrecognised maps to None, which is
# treated as "no opinion" rather than as a mismatch.
FORM_BY_TERM = (
    ("accessory", "accessory"),
    ("tape", "accessory"),
    ("clip", "accessory"),
    ("vent", "accessory"),
    ("mesh", "accessory"),
    ("fastener", "accessory"),
    ("strap", "accessory"),
    ("saddle", "accessory"),
    ("filler", "accessory"),
    ("pipe", "pipe"),
    ("ductlagging", "pipe"),
    ("wrap", "membrane"),
    ("sarking", "membrane"),
    ("membrane", "membrane"),
    ("reflective", "membrane"),
    ("board", "board"),
    ("panel", "board"),
    ("batt", "bulk"),
    ("blanket", "bulk"),
    ("roll", "bulk"),
    ("sheet", "bulk"),
    ("underlay", "underlay"),
)


def product_form(*values) -> str | None:
    """Classify text into a broad product form, most specific term first."""
    blob = " ".join(norm(v) for v in values)
    for term, form in FORM_BY_TERM:
        if term in blob:
            return form
    return None

COLUMNS = {
    "our_sku": "OURSKU",
    "sku": "sku",
    "product_name": "ourproductname",
    "manufacturer": "manufacturername",
    "category": "category",
    "material_type": "materialtype",
    "spec_material_type": "specmaterialtype",
    "product_use": "productuse",
    "spec_id": "specid",
    "spec_family_name": "specfamilyname",
    "thickness_mm": "thickness(mm)",
    "width_mm": "width(mm)",
    "length_mm": "length(mm)",
    "r_value": "R Value / RW / NRC",
    "buy_sell_unit": "buy/sellunit",
    "qty_on_hand": "qtyonhand",
    "tds_url": "tdsurl",
    "sds_url": "sdsurl",
    "image_url": "imageurl",
}


def norm(value) -> str:
    """Collapse to comparable form: the workbook is lowercased and de-spaced."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def words(value) -> list[str]:
    return [w for w in re.sub(r"[^a-z0-9]+", " ", str(value).lower()).split() if w]


def distinctive_tokens(card: dict) -> list[str]:
    """Tokens identifying one family rather than its whole category.

    Short tokens are kept: variant suffixes are often the entire distinction
    between two families. Dropping tokens under four characters merged
    E-Flex ST with E-Flex HT (both reducing to "flex") and lost Kingspan's
    K10/K12/K18 model codes. Only single characters are discarded, since those
    are fragments of hyphenated names ("e-flex") rather than identifiers.
    """
    manufacturer_words = set(words(card.get("manufacturer")))
    out: list[str] = []
    for word in words(card.get("name")) + words(str(card.get("family_id", "")).replace("_", " ")):
        if word in GENERIC_TOKENS or word in manufacturer_words or word in out:
            continue
        if len(word) < 2:
            continue
        out.append(word)
    return out


def family_text(card: dict) -> str:
    parts = [card.get("name", ""), card.get("category", ""), card.get("description") or ""]
    parts += list(card.get("applications", []))[:16]
    parts += list(card.get("keywords", []))[:16]
    return " ".join(str(p) for p in parts).lower()


def load_cards() -> list[dict]:
    with CARDS.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_workbook(path: Path) -> pd.DataFrame:
    frame = pd.read_excel(path, sheet_name=SHEET)
    frame.columns = [str(c).strip() for c in frame.columns]
    missing = [c for c in COLUMNS.values() if c not in frame.columns]
    if missing:
        raise SystemExit(f"workbook is missing expected columns: {missing}")
    active = frame[frame["active?"].astype(str).str.strip().str.lower() == "yes"].copy()
    return active


def match_groups(active: pd.DataFrame, cards: list[dict]) -> dict[tuple[str, str], dict]:
    """Resolve each (manufacturer, spec family) group to a family.

    Grouping first means 118 decisions instead of 1598, and every decision is
    reviewable as a unit.
    """
    by_manufacturer: dict[str, list[dict]] = defaultdict(list)
    for card in cards:
        by_manufacturer[norm(card.get("manufacturer"))].append(card)

    tokens_by_family = {c["family_id"]: distinctive_tokens(c) for c in cards}
    text_by_family = {c["family_id"]: family_text(c) for c in cards}

    decisions: dict[tuple[str, str], dict] = {}
    grouped = active.groupby(
        [active["manufacturername"].map(norm), active["specfamilyname"].astype(str)]
    )
    for (manufacturer, spec_family), group in grouped:
        candidates = by_manufacturer.get(manufacturer, [])
        name_blob = norm(spec_family) + " " + " ".join(norm(v) for v in group["ourproductname"].head(8))
        uses = {norm(u) for value in group["productuse"].head(8) for u in str(value).split("|")}
        materials = {norm(m) for m in group["specmaterialtype"].head(8)}
        materials |= {norm(m) for m in group["materialtype"].head(8)}

        scored = []
        row_form = product_form(spec_family, group["category"].iloc[0], group["productuse"].iloc[0])
        for card in candidates:
            tokens = tokens_by_family[card["family_id"]]
            if not tokens:
                continue
            hits = [t for t in tokens if t in name_blob]
            name_score = len(hits) / len(tokens)
            text = text_by_family[card["family_id"]]
            use_hit = any(
                phrase in text
                for use in uses
                if len(use) > 3
                for phrase in USE_TERMS.get(use, (use,))
            )
            material_hit = any(m and len(m) >= 6 and m[:8] in norm(text) for m in materials)
            card_form = product_form(card.get("name"), card.get("category"))
            # Only a positive disagreement blocks; an unknown form on either
            # side means we simply have no evidence, not evidence against.
            form_conflict = bool(row_form and card_form and row_form != card_form)
            scored.append((name_score, card["family_id"], hits, use_hit, material_hit, form_conflict))

        scored.sort(key=lambda item: (-item[0], item[1]))
        if not scored or scored[0][0] == 0:
            decisions[(manufacturer, spec_family)] = {
                "family_id": None,
                "tier": "unmatched",
                "evidence": "",
            }
            continue

        best = scored[0]
        tied = [s for s in scored[1:] if abs(s[0] - best[0]) < 1e-9]
        corroborated = best[3] or best[4]
        evidence = (
            f"name={best[0]:.2f} tokens={','.join(best[2][:4])} "
            f"use={best[3]} material={best[4]} form_conflict={best[5]}"
        )

        if tied or best[5]:
            # A tie means the name did not discriminate; a form conflict means
            # the best name match is the wrong kind of product. Both are
            # exactly the cases that produced confident nonsense.
            tier = "review"
        elif corroborated and best[0] >= 1.0:
            # Every distinctive token must be present. Partial matches mapped
            # 69 "stonewool spi" pipe SKUs onto E-Therm on the token "therm".
            tier = "high"
        elif best[0] >= 1.0:
            tier = "medium"
        else:
            tier = "review"

        decisions[(manufacturer, spec_family)] = {
            # Only fully corroborated matches are assigned. Medium and review
            # keep their candidate for a human to confirm, but contribute no
            # family link, so an unverified guess cannot reach a recommendation.
            "family_id": best[1] if tier == "high" else None,
            "candidate_family_id": best[1],
            "tier": tier,
            "evidence": evidence,
            "rivals": [s[1] for s in tied[:3]],
        }
    return decisions


SCHEMA = """
CREATE TABLE IF NOT EXISTS product_skus (
    our_sku TEXT PRIMARY KEY,
    sku TEXT,
    product_name TEXT,
    manufacturer TEXT,
    category TEXT,
    material_type TEXT,
    spec_material_type TEXT,
    product_use TEXT,
    spec_id TEXT,
    spec_family_name TEXT,
    thickness_mm REAL,
    width_mm REAL,
    length_mm REAL,
    r_value TEXT,
    buy_sell_unit TEXT,
    qty_on_hand REAL,
    tds_url TEXT,
    sds_url TEXT,
    image_url TEXT,
    family_id TEXT,
    candidate_family_id TEXT,
    match_tier TEXT NOT NULL,
    match_evidence TEXT,
    FOREIGN KEY(family_id) REFERENCES families(family_id)
);
CREATE INDEX IF NOT EXISTS idx_product_skus_sku ON product_skus(sku);
CREATE INDEX IF NOT EXISTS idx_product_skus_family ON product_skus(family_id);
CREATE INDEX IF NOT EXISTS idx_product_skus_manufacturer ON product_skus(manufacturer);
"""


def write_database(rows: list[dict], db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.execute("DELETE FROM product_skus")
        columns = [
            "our_sku", "sku", "product_name", "manufacturer", "category",
            "material_type", "spec_material_type", "product_use", "spec_id",
            "spec_family_name", "thickness_mm", "width_mm", "length_mm",
            "r_value", "buy_sell_unit", "qty_on_hand", "tds_url", "sds_url",
            "image_url", "family_id", "candidate_family_id", "match_tier",
            "match_evidence",
        ]
        conn.executemany(
            f"INSERT INTO product_skus ({','.join(columns)}) VALUES ({','.join('?' * len(columns))})",
            [tuple(r.get(c) for c in columns) for r in rows],
        )
        conn.commit()
    finally:
        conn.close()


def clean(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def build_rows(active: pd.DataFrame, decisions: dict, cards: list[dict]) -> list[dict]:
    form_by_family = {c["family_id"]: product_form(c.get("name"), c.get("category")) for c in cards}
    tokens_by_family = {c["family_id"]: distinctive_tokens(c) for c in cards}
    rows = []
    for _, record in active.iterrows():
        key = (norm(record["manufacturername"]), str(record["specfamilyname"]))
        decision = decisions.get(key, {"family_id": None, "tier": "unmatched", "evidence": ""})
        row = {field: clean(record[column]) for field, column in COLUMNS.items()}
        for numeric in ("thickness_mm", "width_mm", "length_mm", "qty_on_hand"):
            try:
                row[numeric] = float(row[numeric]) if row[numeric] is not None else None
            except ValueError:
                row[numeric] = None

        family_id = decision.get("family_id")
        tier = decision["tier"]
        evidence = decision.get("evidence")

        # A spec-family group is not homogeneous: "bradford|batt" holds batts
        # alongside straps, saddles and fire filler. Assigning the whole group
        # to one family listed accessories as orderable Gold Batts, so each row
        # must independently agree with the family's product form. A human
        # confirmation is a deliberate override and skips both guards.
        auto = evidence != "human_confirmed"

        if family_id and auto:
            # The product name is checked alone first: the group's category is
            # inherited by every row, so "bradford|batt" labels its straps and
            # saddles as batts. The name is the only per-row evidence of what
            # the item actually is.
            name_form = product_form(record["ourproductname"])
            row_form = name_form or product_form(record["category"], record["productuse"])
            family_form = form_by_family.get(family_id)
            if row_form and family_form and row_form != family_form:
                family_id = None
                tier = "review"
                evidence = f"{evidence} row_form={row_form} != family_form={family_form}"

        if family_id and auto:
            # The row must also carry the family's own name. Group membership
            # alone let Bradford's fire filler and roof products inherit the
            # Gold Batts link purely by sharing a spec-family bucket.
            product_blob = norm(record["ourproductname"])
            tokens = tokens_by_family.get(family_id, [])
            if tokens and not any(t in product_blob for t in tokens):
                family_id = None
                tier = "review"
                evidence = f"{evidence} name_lacks_family_token"

        row["family_id"] = family_id
        row["candidate_family_id"] = decision.get("candidate_family_id")
        row["match_tier"] = tier
        row["match_evidence"] = evidence
        rows.append(row)
    return rows


def load_confirmations(path: Path) -> dict[tuple[str, str], str]:
    """Read human-confirmed links from a previous review pass.

    Review effort must survive re-ingestion, so confirmations are applied on top
    of the automatic decisions rather than being overwritten by them.
    """
    if not path.exists():
        return {}
    frame = pd.read_csv(path, dtype=str).fillna("")
    if "confirmed_family_id" not in frame.columns:
        return {}
    confirmed = {}
    for _, row in frame.iterrows():
        family_id = str(row["confirmed_family_id"]).strip()
        if family_id:
            confirmed[(str(row["manufacturer"]).strip(), str(row["spec_family_name"]).strip())] = family_id
    return confirmed


def write_review_csv(decisions: dict, active: pd.DataFrame, path: Path, confirmations: dict) -> None:
    counts = active.groupby(
        [active["manufacturername"].map(norm), active["specfamilyname"].astype(str)]
    ).size()
    records = []
    for (manufacturer, spec_family), decision in sorted(decisions.items()):
        if decision["tier"] in {"high", "medium"}:
            continue
        records.append(
            {
                "manufacturer": manufacturer,
                "spec_family_name": spec_family,
                "sku_count": int(counts.get((manufacturer, spec_family), 0)),
                "match_tier": decision["tier"],
                "suggested_family_id": decision.get("candidate_family_id") or "",
                "rival_family_ids": "|".join(decision.get("rivals", [])),
                "evidence": decision.get("evidence", ""),
                # Preserve any confirmation already recorded for this group.
                "confirmed_family_id": confirmations.get((manufacturer, spec_family), ""),
            }
        )
    pd.DataFrame(records).to_csv(path, index=False, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=WORKBOOK)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()

    if not args.workbook.exists():
        raise SystemExit(f"workbook not found: {args.workbook}")

    active = load_workbook(args.workbook)
    cards = load_cards()
    known_families = {c["family_id"] for c in cards}
    decisions = match_groups(active, cards)

    # Human confirmations override the automatic decision. They are applied
    # after matching so re-running the ingest never discards review work.
    confirmations = load_confirmations(REVIEW_CSV)
    applied = 0
    for key, family_id in confirmations.items():
        if family_id not in known_families:
            print(f"warning: confirmed family_id not in catalogue, ignoring: {family_id}")
            continue
        decision = decisions.setdefault(key, {"tier": "high", "evidence": ""})
        decision["family_id"] = family_id
        decision["candidate_family_id"] = family_id
        decision["tier"] = "high"
        decision["evidence"] = "human_confirmed"
        applied += 1

    rows = build_rows(active, decisions, cards)

    tiers = defaultdict(int)
    for row in rows:
        tiers[row["match_tier"]] += 1

    print(f"active SKUs        : {len(rows)}")
    print(f"unique OURSKU      : {len({r['our_sku'] for r in rows})}")
    print(f"with MYOB sku      : {sum(1 for r in rows if r['sku'])}")
    print(f"linked to a family : {sum(1 for r in rows if r['family_id'])}")
    print(f"human confirmations: {applied}")
    print("match tiers        :", dict(tiers))

    if args.dry_run:
        print("\n(dry run: nothing written)")
        return

    write_database(rows, args.db)
    write_review_csv(decisions, active, REVIEW_CSV, confirmations)
    print(f"\nwrote {len(rows)} rows to {args.db}")
    print(f"review queue -> {REVIEW_CSV}")


if __name__ == "__main__":
    main()
