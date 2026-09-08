"""Lookups over the ingested master SKU table.

The SKU table is the commercial layer over the knowledge base: it answers "what
can I actually order" for a family the recommender has already chosen. It is
deliberately not part of ranking - a SKU has no bearing on whether a product
suits a wall.

Only SKUs whose family link was auto-confirmed are exposed by
``skus_for_family``. Unconfirmed guesses stay in the table with a null
``family_id`` so they can be reviewed, but they must never be presented as
"here is what to order" for a family they may not belong to.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
import re

DB_PATH = Path(__file__).resolve().parent / "data" / "local" / "family_catalogue.sqlite3"
_R_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)")

_FIELDS = (
    "sku, our_sku, product_name, manufacturer, category, material_type, "
    "product_use, thickness_mm, width_mm, length_mm, r_value, buy_sell_unit, "
    "qty_on_hand, tds_url, family_id, match_tier"
)


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(cursor) -> list[dict]:
    return [dict(row) for row in cursor.fetchall()]


def available(db_path: Path | None = None) -> bool:
    """Is the SKU table present? Callers must degrade gracefully if not."""
    path = db_path or DB_PATH
    if not path.exists():
        return False
    conn = _connect(path)
    try:
        found = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='product_skus'"
        ).fetchone()
        return found is not None
    finally:
        conn.close()


def lookup_sku(sku: str, db_path: Path | None = None) -> list[dict]:
    """Find a product by MYOB/online SKU, falling back to the internal code.

    Returns a list because ``sku`` is not unique in the source data: pack and
    unit variants legitimately share one MYOB code.
    """
    if not sku or not sku.strip():
        return []
    needle = sku.strip().lower()
    conn = _connect(db_path)
    try:
        rows = _rows(
            conn.execute(
                f"SELECT {_FIELDS} FROM product_skus WHERE lower(sku) = ? ORDER BY our_sku",
                (needle,),
            )
        )
        if rows:
            return rows
        return _rows(
            conn.execute(
                f"SELECT {_FIELDS} FROM product_skus WHERE lower(our_sku) = ? ORDER BY our_sku",
                (needle,),
            )
        )
    finally:
        conn.close()


def skus_for_family(family_id: str, limit: int = 25, db_path: Path | None = None) -> list[dict]:
    """Confirmed orderable SKUs for a recommended family, in-stock first."""
    if not family_id:
        return []
    conn = _connect(db_path)
    try:
        return _rows(
            conn.execute(
                f"""SELECT {_FIELDS} FROM product_skus
                    WHERE family_id = ? AND match_tier = 'high'
                    ORDER BY (COALESCE(qty_on_hand, 0) > 0) DESC,
                             thickness_mm, width_mm, our_sku
                    LIMIT ?""",
                (family_id, limit),
            )
        )
    finally:
        conn.close()


def skus_matching(
    family_id: str,
    width: float | None = None,
    thickness: float | None = None,
    rvalue: float | None = None,
    limit: int = 10,
    db_path: Path | None = None,
) -> list[dict]:
    """Confirmed SKUs for a family, narrowed to a width/thickness/R-value.

    Tolerances mirror ``size_index.query`` (+-5mm width, +-2mm thickness,
    +-0.15 R-value) so an availability answer and its SKU list agree on what
    counts as a match. Only ``match_tier = 'high'`` rows are eligible, for the
    same reason as ``skus_for_family``: an unconfirmed guess must not be quoted
    as an orderable product.
    """
    rows = skus_for_family(family_id, limit=max(limit, 200), db_path=db_path)
    if width is not None:
        rows = [r for r in rows if r["width_mm"] is not None and abs(r["width_mm"] - width) <= 5]
    if thickness is not None:
        rows = [r for r in rows if r["thickness_mm"] is not None and abs(r["thickness_mm"] - thickness) <= 2]
    if rvalue is not None:
        def _r(value) -> float | None:
            if not value:
                return None
            match = _R_NUM_RE.search(str(value))
            return float(match.group(1)) if match else None

        rows = [r for r in rows if (_r(r["r_value"]) is not None and abs(_r(r["r_value"]) - rvalue) <= 0.15)]
    return rows[:limit]


def coverage(db_path: Path | None = None) -> dict:
    """Counts for diagnostics and tests."""
    conn = _connect(db_path)
    try:
        total, with_sku, linked = conn.execute(
            """SELECT COUNT(*),
                      SUM(CASE WHEN sku IS NOT NULL THEN 1 ELSE 0 END),
                      SUM(CASE WHEN family_id IS NOT NULL THEN 1 ELSE 0 END)
               FROM product_skus"""
        ).fetchone()
        tiers = {
            row[0]: row[1]
            for row in conn.execute("SELECT match_tier, COUNT(*) FROM product_skus GROUP BY 1")
        }
        families = conn.execute(
            "SELECT COUNT(DISTINCT family_id) FROM product_skus WHERE family_id IS NOT NULL"
        ).fetchone()[0]
        return {
            "total_skus": total,
            "with_myob_sku": with_sku or 0,
            "linked_to_family": linked or 0,
            "families_covered": families,
            "tiers": tiers,
        }
    finally:
        conn.close()
