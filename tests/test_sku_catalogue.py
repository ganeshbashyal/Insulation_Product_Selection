"""Tests for the master SKU catalogue lookups.

These build a small database in a temp file rather than reading the real one,
so they assert behaviour rather than today's ingest counts.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sku_catalogue


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "cat.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE product_skus (
            our_sku TEXT PRIMARY KEY, sku TEXT, product_name TEXT,
            manufacturer TEXT, category TEXT, material_type TEXT,
            spec_material_type TEXT, product_use TEXT, spec_id TEXT,
            spec_family_name TEXT, thickness_mm REAL, width_mm REAL,
            length_mm REAL, r_value TEXT, buy_sell_unit TEXT, qty_on_hand REAL,
            tds_url TEXT, sds_url TEXT, image_url TEXT, family_id TEXT,
            candidate_family_id TEXT, match_tier TEXT NOT NULL, match_evidence TEXT
        );
        """
    )
    rows = [
        # our_sku, sku, name, family_id, tier, thickness, qty
        ("A1", "myob-1", "gold batt r2.0", "BRADFORD_GOLD_BATTS", "high", 90.0, 0.0),
        ("A2", "myob-1", "gold batt r2.0 pack", "BRADFORD_GOLD_BATTS", "high", 90.0, 12.0),
        ("A3", "myob-3", "gold batt r2.5", "BRADFORD_GOLD_BATTS", "high", 140.0, 0.0),
        ("B1", None, "underslab 80mm", None, "unmatched", 80.0, 3.0),
        ("C1", "myob-9", "maybe a batt", None, "review", None, 0.0),
    ]
    conn.executemany(
        """INSERT INTO product_skus
           (our_sku, sku, product_name, family_id, match_tier, thickness_mm, qty_on_hand)
           VALUES (?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    conn.close()
    return path


def test_lookup_by_myob_sku_returns_all_sharing_rows(db):
    """sku is not unique: pack and unit variants legitimately share one code."""
    rows = sku_catalogue.lookup_sku("myob-1", db_path=db)
    assert {r["our_sku"] for r in rows} == {"A1", "A2"}


def test_lookup_is_case_insensitive_and_trims(db):
    assert sku_catalogue.lookup_sku("  MYOB-3 ", db_path=db)[0]["our_sku"] == "A3"


def test_lookup_falls_back_to_internal_sku(db):
    """31 active products have no MYOB code; they must still be findable."""
    rows = sku_catalogue.lookup_sku("B1", db_path=db)
    assert len(rows) == 1
    assert rows[0]["sku"] is None


def test_unknown_and_empty_lookups_are_empty(db):
    assert sku_catalogue.lookup_sku("nope", db_path=db) == []
    assert sku_catalogue.lookup_sku("", db_path=db) == []
    assert sku_catalogue.skus_for_family("", db_path=db) == []


def test_only_confirmed_links_are_offered_as_orderable(db):
    """An unconfirmed guess must never be presented as what to order.

    C1 has match_tier 'review' and no family; it must not appear for any
    family, or the bot would quote a product it cannot stand behind.
    """
    rows = sku_catalogue.skus_for_family("BRADFORD_GOLD_BATTS", db_path=db)
    assert {r["our_sku"] for r in rows} == {"A1", "A2", "A3"}


def test_in_stock_items_are_listed_first(db):
    rows = sku_catalogue.skus_for_family("BRADFORD_GOLD_BATTS", db_path=db)
    assert rows[0]["our_sku"] == "A2"


def test_limit_is_respected(db):
    assert len(sku_catalogue.skus_for_family("BRADFORD_GOLD_BATTS", limit=2, db_path=db)) == 2


def test_coverage_counts(db):
    stats = sku_catalogue.coverage(db_path=db)
    assert stats["total_skus"] == 5
    assert stats["with_myob_sku"] == 4
    assert stats["linked_to_family"] == 3
    assert stats["families_covered"] == 1


@pytest.fixture
def sized_db(tmp_path):
    """Rows carrying width/R-value, for exercising skus_matching's tolerances."""
    path = tmp_path / "sized.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE product_skus (
            our_sku TEXT PRIMARY KEY, sku TEXT, product_name TEXT,
            manufacturer TEXT, category TEXT, material_type TEXT,
            spec_material_type TEXT, product_use TEXT, spec_id TEXT,
            spec_family_name TEXT, thickness_mm REAL, width_mm REAL,
            length_mm REAL, r_value TEXT, buy_sell_unit TEXT, qty_on_hand REAL,
            tds_url TEXT, sds_url TEXT, image_url TEXT, family_id TEXT,
            candidate_family_id TEXT, match_tier TEXT NOT NULL, match_evidence TEXT
        );
        """
    )
    rows = [
        # our_sku, sku, family_id, tier, thickness, width, r_value
        ("S1", "s1", "BRADFORD_GOLD_BATTS", "high", 90.0, 430.0, "R2.0"),
        ("S2", "s2", "BRADFORD_GOLD_BATTS", "high", 90.0, 580.0, "R2.0"),
        ("S3", "s3", "BRADFORD_GOLD_BATTS", "high", 140.0, 430.0, "R2.5"),
        # Same width/thickness/R as S1 but unconfirmed - must not be offered.
        ("S4", "s4", None, "review", 90.0, 430.0, "R2.0"),
    ]
    conn.executemany(
        """INSERT INTO product_skus
           (our_sku, sku, family_id, match_tier, thickness_mm, width_mm, r_value)
           VALUES (?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    conn.close()
    return path


def test_skus_matching_filters_by_width_thickness_and_rvalue(sized_db):
    rows = sku_catalogue.skus_matching(
        "BRADFORD_GOLD_BATTS", width=430, thickness=90, rvalue=2.0, db_path=sized_db
    )
    assert {r["our_sku"] for r in rows} == {"S1"}


def test_skus_matching_tolerates_small_deviations(sized_db):
    """Tolerances mirror size_index.query so an availability answer and its
    SKU list agree on what counts as a match (+-5mm width, +-2mm thickness,
    +-0.15 R-value)."""
    rows = sku_catalogue.skus_matching(
        "BRADFORD_GOLD_BATTS", width=433, thickness=91, rvalue=2.05, db_path=sized_db
    )
    assert {r["our_sku"] for r in rows} == {"S1"}


def test_skus_matching_excludes_out_of_tolerance_rows(sized_db):
    rows = sku_catalogue.skus_matching(
        "BRADFORD_GOLD_BATTS", width=430, thickness=90, rvalue=2.5, db_path=sized_db
    )
    assert rows == []


def test_skus_matching_never_returns_unconfirmed_rows(sized_db):
    """S4 shares S1's width/thickness/R exactly but is still under review."""
    rows = sku_catalogue.skus_matching(
        "BRADFORD_GOLD_BATTS", width=430, thickness=90, rvalue=2.0, db_path=sized_db
    )
    assert all(r["our_sku"] != "S4" for r in rows)


def test_skus_matching_with_no_constraints_returns_all_confirmed(sized_db):
    rows = sku_catalogue.skus_matching("BRADFORD_GOLD_BATTS", db_path=sized_db)
    assert {r["our_sku"] for r in rows} == {"S1", "S2", "S3"}


def test_available_is_false_without_a_database(tmp_path):
    """Callers must degrade gracefully when the SKU table has not been built."""
    assert sku_catalogue.available(db_path=tmp_path / "missing.sqlite3") is False
