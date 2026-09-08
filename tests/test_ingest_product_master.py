"""Tests for the master SKU ingest matcher.

The matcher's job is to be *conservative*. Every rule here exists because the
looser version produced a confidently wrong link on the real workbook.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ingest_product_master as ing


def card(family_id, name, manufacturer, category, **extra):
    base = {
        "family_id": family_id,
        "name": name,
        "manufacturer": manufacturer,
        "category": category,
        "description": extra.get("description", ""),
        "applications": extra.get("applications", []),
        "keywords": extra.get("keywords", []),
    }
    return base


def frame(rows):
    columns = {
        "OURSKU": "sku_internal", "sku": "sku_myob", "ourproductname": "name",
        "manufacturername": "manufacturer", "category": "category",
        "materialtype": "material", "specmaterialtype": "material",
        "productuse": "use", "specid": "spec", "specfamilyname": "spec_family",
        "thickness(mm)": "thickness", "width(mm)": "width", "length(mm)": "length",
        "R Value / RW / NRC": "r_value", "buy/sellunit": "unit",
        "qtyonhand": "qty", "tdsurl": "tds", "sdsurl": "sds", "imageurl": "image",
    }
    data = []
    for row in rows:
        data.append({col: row.get(key, "") for col, key in columns.items()})
    return pd.DataFrame(data)


def test_distinctive_tokens_keep_variant_suffixes():
    """E-Flex ST and E-Flex HT differ only by suffix.

    Dropping short tokens merged them, so 16 high-temperature pipe SKUs were
    linked to the standard-temperature family.
    """
    st = ing.distinctive_tokens(card("THERMOTEC_E_FLEX_ST", "Thermotec E-Flex ST", "Thermotec", "Pipe"))
    ht = ing.distinctive_tokens(card("THERMOTEC_E_FLEX_HT", "Thermotec E-Flex HT", "Thermotec", "Pipe"))
    assert "st" in st and "ht" in ht
    assert st != ht


def test_distinctive_tokens_keep_model_codes():
    """Kingspan families are named K10/K12/K18; the code is the only signal."""
    assert "k10" in ing.distinctive_tokens(card("KINGSPAN_K10", "Kingspan Kooltherm K10", "Kingspan", "Board"))


def test_distinctive_tokens_drop_generic_and_manufacturer_words():
    tokens = ing.distinctive_tokens(card("BRADFORD_GOLD_BATTS", "Bradford Gold Batts", "Bradford", "Batt"))
    assert tokens == ["gold"]


def test_product_form_separates_accessories_from_products():
    """A strap must not be classified as the batt it fastens."""
    assert ing.product_form("bradoptimostrapspk") == "accessory"
    assert ing.product_form("goldbatts-430mmwider2.0") == "bulk"
    assert ing.product_form("proctor gable vent") == "accessory"


def test_product_form_returns_none_when_unknown():
    """Unknown form means no evidence, not evidence of mismatch."""
    assert ing.product_form("mystery item 1234") is None


def test_group_with_tied_candidates_goes_to_review():
    """If the name cannot discriminate, we must not pick one arbitrarily."""
    cards = [
        card("ECOWOOL_ACOUSTIC_PARTITION_BATT", "Ecowool Acoustic Partition Batt", "Ecowool", "Batt"),
        card("ECOWOOL_ACOUSTIC_PARTITION_ROLL", "Ecowool Acoustic Partition Roll", "Ecowool", "Roll"),
    ]
    active = frame([
        {
            "sku_internal": "E1", "sku_myob": "e1", "name": "ecowoolpartitionbatt",
            "manufacturer": "ecowool", "category": "batt", "material": "polyester",
            "use": "internalwall", "spec_family": "ecowool|batt|partition",
        }
    ])
    decisions = ing.match_groups(active, cards)
    decision = next(iter(decisions.values()))
    assert decision["tier"] == "review"
    assert decision["family_id"] is None


def test_partial_token_match_is_not_auto_accepted():
    """"stonewool spi" matched E-Therm on the token "therm" alone.

    That linked 69 stonewool pipe SKUs to a reflective membrane.
    """
    cards = [card("THERMOTEC_E_THERM", "Thermotec E-Therm", "Thermotec", "Reflective insulation")]
    active = frame([
        {
            "sku_internal": "T1", "sku_myob": "t1", "name": "stonewoolspipipesection",
            "manufacturer": "thermotec", "category": "pipeinsulation", "material": "stonewool",
            "use": "pipe", "spec_family": "thermotec|pipeinsulation|stonewoolspi",
        }
    ])
    decisions = ing.match_groups(active, cards)
    assert next(iter(decisions.values()))["family_id"] is None


def test_row_without_the_family_name_is_not_linked():
    """Sharing a spec-family bucket is not enough to inherit the link.

    Bradford's straps, saddles and fire filler sit in "bradford|batt" and were
    being listed as orderable Gold Batts.
    """
    cards = [card("BRADFORD_GOLD_BATTS", "Bradford Gold Batts", "Bradford", "Batt",
                  applications=["ceiling"], keywords=["glasswool"])]
    active = frame([
        {
            "sku_internal": "G1", "sku_myob": "g1", "name": "goldbatts-430mmwider2.0",
            "manufacturer": "bradford", "category": "batt", "material": "glasswool",
            "use": "ceiling", "spec_family": "bradford|batt",
        },
        {
            "sku_internal": "G2", "sku_myob": "g2", "name": "bradoptimostrapspk",
            "manufacturer": "bradford", "category": "batt", "material": "glasswool",
            "use": "ceiling", "spec_family": "bradford|batt",
        },
    ])
    decisions = ing.match_groups(active, cards)
    rows = {r["our_sku"]: r for r in ing.build_rows(active, decisions, cards)}

    assert rows["G1"]["family_id"] == "BRADFORD_GOLD_BATTS"
    assert rows["G2"]["family_id"] is None
    assert rows["G2"]["match_tier"] == "review"


def test_unmatched_manufacturer_group_is_recorded_not_guessed():
    cards = [card("KNAUF_BATT", "Knauf Batt", "Knauf", "Batt")]
    active = frame([
        {
            "sku_internal": "X1", "sku_myob": "x1", "name": "somethingelse",
            "manufacturer": "knauf", "category": "batt", "material": "glasswool",
            "use": "ceiling", "spec_family": "knauf|batt|unknown",
        }
    ])
    decisions = ing.match_groups(active, cards)
    assert next(iter(decisions.values()))["tier"] in {"unmatched", "review"}
    assert next(iter(decisions.values()))["family_id"] is None


def test_confirmations_round_trip_through_the_review_csv(tmp_path):
    path = tmp_path / "review.csv"
    pd.DataFrame(
        [
            {"manufacturer": "knauf", "spec_family_name": "knauf|batt|x",
             "confirmed_family_id": "KNAUF_BATT"},
            {"manufacturer": "knauf", "spec_family_name": "knauf|batt|y",
             "confirmed_family_id": ""},
        ]
    ).to_csv(path, index=False)

    assert ing.load_confirmations(path) == {("knauf", "knauf|batt|x"): "KNAUF_BATT"}


def test_missing_review_csv_yields_no_confirmations(tmp_path):
    assert ing.load_confirmations(tmp_path / "absent.csv") == {}


def test_human_confirmation_overrides_the_per_row_guards():
    """A person confirming a link must not be second-guessed by the heuristics.

    The row name here shares no token with the family, which the automatic
    path rejects; the confirmation must still stand.
    """
    cards = [card("KNAUF_BATT", "Knauf Batt", "Knauf", "Batt")]
    active = frame([
        {
            "sku_internal": "K1", "sku_myob": "k1", "name": "unrelatedname",
            "manufacturer": "knauf", "category": "batt", "material": "glasswool",
            "use": "ceiling", "spec_family": "knauf|batt|x",
        }
    ])
    decisions = {
        ("knauf", "knauf|batt|x"): {
            "family_id": "KNAUF_BATT",
            "candidate_family_id": "KNAUF_BATT",
            "tier": "high",
            "evidence": "human_confirmed",
        }
    }
    rows = ing.build_rows(active, decisions, cards)
    assert rows[0]["family_id"] == "KNAUF_BATT"
