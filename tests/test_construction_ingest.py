"""Tests for the local construction data ingestion engine.

Everything here runs offline: no downloads and no Ollama calls.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from construction_ingest import construction_matrix as matrix
from construction_ingest import db_setup
from construction_ingest.construction_matrix import FramingType, Phase
from construction_ingest.local_pdf_parser import (
    ProductRecord,
    _parse_model_json,
    regex_prefill,
)
from construction_ingest.main import Query, match_products, parse_query, render, run_query


# ---------------------------------------------------------------------------
# db_setup
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def zone_db(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("zones") / "construction_postcodes.db"
    db_setup.build_database(db_path=path, offline=True)
    return path


def test_normalise_postcode_pads_and_rejects():
    assert db_setup.normalise_postcode("800") == "0800"
    assert db_setup.normalise_postcode(3000) == "3000"
    assert db_setup.normalise_postcode("postcode 3000") == "3000"
    assert db_setup.normalise_postcode("abcd") is None
    assert db_setup.normalise_postcode("") is None


def test_coerce_zone_range():
    assert db_setup.coerce_zone("Zone 6") == 6
    assert db_setup.coerce_zone(8) == 8
    assert db_setup.coerce_zone("9") is None
    assert db_setup.coerce_zone("") is None


@pytest.mark.parametrize(
    ("postcode", "state", "zone"),
    [
        ("3000", "VIC", 6),  # Melbourne
        ("2000", "NSW", 5),  # Sydney
        ("4000", "QLD", 2),  # Brisbane
        ("5000", "SA", 5),  # Adelaide
        ("6000", "WA", 5),  # Perth
        ("7000", "TAS", 7),  # Hobart
        ("0800", "NT", 1),  # Darwin
        ("2600", "ACT", 7),  # Canberra
        ("4870", "QLD", 1),  # Cairns
    ],
)
def test_capital_city_zones(zone_db, postcode, state, zone):
    connection = db_setup.connect(zone_db)
    try:
        record = db_setup.lookup_postcode(connection, postcode)
    finally:
        connection.close()
    assert record is not None
    assert record["state"] == state
    assert record["climate_zone"] == zone


def test_alpine_postcodes_override_the_surrounding_range(zone_db):
    connection = db_setup.connect(zone_db)
    try:
        for postcode in db_setup.ALPINE_POSTCODES:
            record = db_setup.lookup_postcode(connection, postcode)
            assert record is not None, postcode
            assert record["climate_zone"] == 8, postcode
    finally:
        connection.close()


def test_every_seeded_postcode_has_a_valid_zone(zone_db):
    connection = db_setup.connect(zone_db)
    try:
        bad = connection.execute(
            "SELECT COUNT(*) FROM postcode_zones WHERE climate_zone NOT BETWEEN 1 AND 8"
        ).fetchone()[0]
        total = connection.execute("SELECT COUNT(DISTINCT postcode) FROM postcode_zones").fetchone()[0]
    finally:
        connection.close()
    assert bad == 0
    assert total > 6000


def test_seeded_rows_are_flagged_for_confirmation(zone_db):
    connection = db_setup.connect(zone_db)
    try:
        record = db_setup.lookup_postcode(connection, "3000")
    finally:
        connection.close()
    assert record["confidence"] == "range_seed"
    assert record["requires_confirmation"] is True
    assert "ABCB Climate Map" in record["confirmation_note"]


def test_unknown_postcode_returns_none(zone_db):
    connection = db_setup.connect(zone_db)
    try:
        assert db_setup.lookup_postcode(connection, "9999") is None
    finally:
        connection.close()


def test_authoritative_csv_overrides_the_seed(tmp_path):
    db_path = tmp_path / "override.db"
    db_setup.build_database(db_path=db_path, offline=True)
    csv_path = tmp_path / "zones.csv"
    csv_path.write_text(
        "postcode,locality,state,climate zone\n3000,Melbourne,VIC,6\n3000,Docklands,VIC,6\n",
        encoding="utf-8",
    )
    db_setup.build_database(db_path=db_path, csv_paths=[csv_path], offline=True)

    connection = db_setup.connect(db_path)
    try:
        record = db_setup.lookup_postcode(connection, "3000", suburb="Docklands")
    finally:
        connection.close()
    assert record["confidence"] == "authoritative"
    assert record["suburb"] == "Docklands"
    assert record["climate_zone"] == 6


def test_non_climate_zone_column_is_ignored():
    """An electricity 'chargezone' column must not be read as a climate zone."""
    text = "postcode,locality,state,chargezone\n3000,Melbourne,VIC,ADE\n3001,Melbourne,VIC,ADE\n"
    rows = db_setup.parse_postcode_csv(text, "fixture.csv")
    assert rows
    assert all(row.confidence == "range_seed" for row in rows)
    assert all(row.climate_zone == 6 for row in rows)


def test_csv_without_a_postcode_column_yields_nothing():
    assert db_setup.parse_postcode_csv("name,state\nFoo,VIC\n", "bad.csv") == []


def test_download_refuses_non_http_scheme():
    assert db_setup.download_csv("file:///etc/passwd") is None


def test_ncc_volume_by_building_class():
    assert db_setup.ncc_volume_for("Class 1") == "Vol 2 (ABCB Housing Provisions)"
    assert db_setup.ncc_volume_for("10") == "Vol 2 (ABCB Housing Provisions)"
    assert db_setup.ncc_volume_for("Class 2") == "Vol 1"
    assert db_setup.ncc_volume_for(None) == db_setup.DEFAULT_NCC_VOLUME


def test_export_json_round_trip(zone_db, tmp_path):
    connection = db_setup.connect(zone_db)
    try:
        path = db_setup.export_json(connection, tmp_path / "zones.json")
    finally:
        connection.close()
    mapping = json.loads(path.read_text(encoding="utf-8"))
    assert mapping["3000"]["climate_zone"] == 6
    assert mapping["0800"]["climate_zone"] == 1


# ---------------------------------------------------------------------------
# construction_matrix
# ---------------------------------------------------------------------------


def test_steel_requires_a_thermal_break_and_timber_does_not():
    steel = matrix.FRAMING_PROFILES[FramingType.STEEL]
    timber = matrix.FRAMING_PROFILES[FramingType.TIMBER]
    assert steel.thermal_break_required is True
    assert timber.thermal_break_required is False
    assert steel.thermal_conductivity_w_mk > timber.thermal_conductivity_w_mk * 100
    assert "R0.2" in steel.thermal_break_provision


def test_steel_framing_phase_states_the_r02_thermal_break():
    rules = matrix.rules_for(phase=Phase.FRAMING, framing_type=FramingType.STEEL, climate_zone=6)
    text = " ".join(rule.requirement for rule in rules)
    assert "R0.2" in text
    assert any("13.2" in rule.provision for rule in rules)


def test_timber_framing_phase_has_no_thermal_break_rule():
    rules = matrix.rules_for(phase=Phase.FRAMING, framing_type=FramingType.TIMBER, climate_zone=6)
    assert not any("thermal break" in rule.requirement.casefold() for rule in rules)


@pytest.mark.parametrize(
    ("zone", "minimum", "classes"),
    [
        (1, None, ["Class 1", "Class 2", "Class 3", "Class 4"]),
        (3, None, ["Class 1", "Class 2", "Class 3", "Class 4"]),
        (4, 0.143, ["Class 3", "Class 4"]),
        (5, 0.143, ["Class 3", "Class 4"]),
        (6, 1.14, ["Class 4"]),
        (8, 1.14, ["Class 4"]),
    ],
)
def test_membrane_permeance_thresholds_match_ncc_1081(zone, minimum, classes):
    requirement = matrix.membrane_requirement(zone)
    assert requirement["minimum_vapour_permeance_ug_per_Ns"] == minimum
    assert requirement["membrane_classes"] == classes


def test_membrane_requirement_rejects_an_invalid_zone():
    with pytest.raises(ValueError):
        matrix.membrane_requirement(9)


def test_roof_space_ventilation_only_applies_to_zones_6_to_8():
    for zone in range(1, 9):
        rules = matrix.rules_for(phase=Phase.WRAPPING, climate_zone=zone)
        has_rule = any("10.8.3" in rule.provision for rule in rules)
        assert has_rule is (zone in matrix.COOL_ZONES), zone


def test_build_sequence_covers_every_phase_in_order():
    sequence = matrix.build_sequence("steel", 6)
    assert [block["phase"] for block in sequence] == [phase.value for phase in matrix.PHASE_ORDER]
    assert all(block["rules"] for block in sequence)


def test_coerce_framing_parses_loose_text():
    assert matrix.coerce_framing("steel frame") is FramingType.STEEL
    assert matrix.coerce_framing("light gauge metal") is FramingType.STEEL
    assert matrix.coerce_framing("Timber stud wall") is FramingType.TIMBER
    with pytest.raises(ValueError):
        matrix.coerce_framing("brick veneer")


def test_rules_for_rejects_an_invalid_zone():
    with pytest.raises(ValueError):
        matrix.rules_for(climate_zone=0)


def test_every_rule_cites_a_provision():
    for rule in matrix.CONSTRUCTION_RULES:
        assert rule.provision.strip(), rule.requirement
        assert rule.climate_zones <= matrix.ALL_ZONES


def test_matrix_never_publishes_a_zone_r_value():
    """Total R-values are project-specific; the matrix must not tabulate them."""
    payload = json.loads(matrix.to_json())
    assert "scope_note" in payload
    informational = [r for r in payload["rules"] if r["severity"] == "informational"]
    assert any("project-specific" in r["material"].casefold() for r in informational)


# ---------------------------------------------------------------------------
# local_pdf_parser
# ---------------------------------------------------------------------------

SAMPLE_TDS_TEXT = """Fletcher Insulation - Sisalation Vapawrap Residential Wall Wrap
Technical Data Sheet
Material: vapour permeable non-woven polymer breather membrane
Vapour control: Class 4 to AS/NZS 4200.1
Vapour permeance: 1.72 ug/N.s
Suitable for timber and steel framed residential walls
"""


def test_regex_prefill_extracts_membrane_facts():
    data = regex_prefill(SAMPLE_TDS_TEXT, "vapawrap.pdf")
    record = ProductRecord.model_validate(data)
    assert record.manufacturer == "Fletcher"
    assert record.material_type == "Breather membrane"
    assert record.vapour_permeance_class == "Class 4"
    assert record.vapour_permeance_ug_per_Ns == 1.72
    assert set(record.framing_compatibility) == {"Timber", "Steel"}
    assert "AS/NZS 4200.1" in data["standards_cited"]


def test_product_record_normalises_messy_values():
    record = ProductRecord.model_validate(
        {
            "declared_r_value": ["R 2.5", 4.0, "rubbish"],
            "vapour_permeance_class": "class4",
            "framing_compatibility": "steel and timber",
            "material_type": "glass wool batt",
        }
    )
    assert record.declared_r_value == ["R2.5", "R4"]
    assert record.vapour_permeance_class == "Class 4"
    assert set(record.framing_compatibility) == {"Steel", "Timber"}
    assert record.material_type == "Glasswool"


def test_product_record_defaults_are_safe():
    record = ProductRecord()
    assert record.manufacturer == "Unknown"
    assert record.vapour_permeance_class == "Not stated"
    assert record.declared_r_value == []
    assert record.ncc_compliance_notes == ""


def test_parse_model_json_tolerates_fences_and_prose():
    assert _parse_model_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _parse_model_json('Here you go: {"a": 2} - hope that helps') == {"a": 2}
    assert _parse_model_json("not json at all") is None
    assert _parse_model_json("") is None
    assert _parse_model_json("[1, 2]") is None


# ---------------------------------------------------------------------------
# main pipeline
# ---------------------------------------------------------------------------


def test_parse_query_reads_postcode_framing_and_phase():
    query = parse_query("What wrap and insulation stage applies to a steel-framed house in postcode 3000?")
    assert query.postcode == "3000"
    assert query.framing is FramingType.STEEL
    assert Phase.WRAPPING in query.phases
    assert Phase.INSULATION in query.phases


def test_parse_query_detects_timber():
    query = parse_query("timber framed home in 4000, what batts do I need?")
    assert query.framing is FramingType.TIMBER
    assert query.postcode == "4000"


def test_parse_query_without_a_postcode():
    query = parse_query("do I need a thermal break on steel studs?")
    assert query.postcode is None
    assert query.framing is FramingType.STEEL


def test_run_query_melbourne_steel_returns_zone_6_class_4(zone_db, tmp_path):
    answer = run_query(
        "What wrap and insulation stage applies to a steel-framed house in postcode 3000 (Melbourne)?",
        db_path=zone_db,
        product_knowledge=tmp_path / "missing.json",
    )
    assert answer["location"]["climate_zone"] == 6
    assert answer["membrane_requirement"]["minimum_vapour_permeance_ug_per_Ns"] == 1.14
    assert answer["framing"]["thermal_break_required"] is True

    requirements = " ".join(
        rule["requirement"] for block in answer["rules"] for rule in block["rules"]
    )
    assert "R0.2" in requirements
    assert "1.14" in requirements
    assert render(answer)


def test_run_query_brisbane_timber_has_no_permeance_minimum(zone_db, tmp_path):
    answer = run_query(
        "timber framed house in postcode 4000 Brisbane, what wall wrap?",
        db_path=zone_db,
        product_knowledge=tmp_path / "missing.json",
    )
    assert answer["location"]["climate_zone"] == 2
    assert answer["membrane_requirement"]["minimum_vapour_permeance_ug_per_Ns"] is None
    assert answer["framing"]["thermal_break_required"] is False


def test_run_query_warns_when_the_database_is_missing(tmp_path):
    answer = run_query(
        Query(postcode="3000", raw="test"),
        db_path=tmp_path / "absent.db",
        product_knowledge=tmp_path / "missing.json",
    )
    assert answer["location"] is None
    assert any("--build" in warning for warning in answer["warnings"])


def test_run_query_without_a_postcode_still_returns_framing_rules(zone_db, tmp_path):
    answer = run_query(
        "do I need a thermal break on steel studs?",
        db_path=zone_db,
        product_knowledge=tmp_path / "missing.json",
    )
    assert answer["location"] is None
    assert answer["framing"]["thermal_break_required"] is True
    assert any("no postcode" in warning for warning in answer["warnings"])


def _membrane(**overrides) -> ProductRecord:
    data = {
        "manufacturer": "Demo",
        "product_name": "Demo Wrap",
        "material_type": "Breather membrane",
        "vapour_permeance_class": "Class 4",
        "vapour_permeance_ug_per_Ns": 1.72,
        "framing_compatibility": ["Timber", "Steel"],
    }
    data.update(overrides)
    return ProductRecord.model_validate(data)


def test_matching_flags_a_membrane_below_the_zone_threshold():
    foil = _membrane(
        product_name="Foil Sarking",
        material_type="Reflective foil",
        vapour_permeance_class="Class 1",
        vapour_permeance_ug_per_Ns=0.02,
    )
    results = match_products([foil], climate_zone=6, framing=FramingType.TIMBER, phases=[])
    assert results[0]["screening_status"] == "flagged"
    assert any("below the zone 6 minimum" in flag for flag in results[0]["flags"])


def test_matching_accepts_a_compliant_membrane():
    results = match_products([_membrane()], climate_zone=6, framing=FramingType.STEEL, phases=[])
    assert results[0]["screening_status"] == "candidate"
    assert not results[0]["flags"]


def test_matching_flags_incompatible_framing():
    timber_only = _membrane(framing_compatibility=["Timber"])
    results = match_products([timber_only], climate_zone=6, framing=FramingType.STEEL, phases=[])
    assert any("does not list Steel" in flag for flag in results[0]["flags"])


def test_matching_flags_a_membrane_with_no_extracted_permeance():
    unknown = _membrane(vapour_permeance_ug_per_Ns=None)
    results = match_products([unknown], climate_zone=7, framing=None, phases=[])
    assert any("not extracted" in flag for flag in results[0]["flags"])


def test_matching_never_claims_compliance():
    results = match_products([_membrane()], climate_zone=6, framing=FramingType.STEEL, phases=[])
    text = json.dumps(results).casefold()
    assert "ncc compliant" not in text
    assert "complies with" not in text
