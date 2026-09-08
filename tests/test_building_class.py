"""Offline tests for the NCC building-class ingestion module.

No network, no Ollama, no reliance on the checked-in source file being present.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from construction_ingest import building_class as bc


# --------------------------------------------------------------------------
# JSON repair / concatenated object decoding
# --------------------------------------------------------------------------


def test_repair_json_strips_latex_comparison_operators():
    raw = r'{"acoustic_requirement": "$Rw + Ctr \ge 50$"}'
    obj = json.loads(bc.repair_json_text(raw))
    assert obj["acoustic_requirement"] == "Rw + Ctr >= 50"


def test_repair_json_handles_less_than_or_equal():
    raw = r'{"a": "$U \le 2.0$"}'
    assert json.loads(bc.repair_json_text(raw))["a"] == "U <= 2.0"


def test_repair_json_preserves_valid_escapes():
    raw = '{"a": "line\\nbreak", "b": "quote\\"inside"}'
    obj = json.loads(bc.repair_json_text(raw))
    assert obj["a"] == "line\nbreak"
    assert obj["b"] == 'quote"inside'


def test_iter_json_objects_reads_concatenated_objects():
    raw = '{"building_type": "Class 1a House"}\n\n{"building_type": "Class 2 Apartments"}'
    objects = bc.iter_json_objects(raw)
    assert [o["building_type"] for o in objects] == [
        "Class 1a House",
        "Class 2 Apartments",
    ]


def test_iter_json_objects_reads_a_plain_array():
    raw = '[{"building_type": "Class 5 Office"}]'
    assert len(bc.iter_json_objects(raw)) == 1


# --------------------------------------------------------------------------
# Class-code extraction
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "building_type,expected",
    [
        ("Class 1a Single Dwelling Residential", ["1a"]),
        ("Class 5 (Office) & Class 6 (Retail)", ["5", "6"]),
        ("Class 10a (Garage), Class 10b (Fence)", ["10a", "10b"]),
        ("Class 7a Carpark", ["7a"]),
        ("Warehouse with no class marker", []),
    ],
)
def test_extract_class_codes(building_type, expected):
    assert bc.extract_class_codes(building_type) == expected


def test_extract_class_codes_expands_a_span():
    codes = bc.extract_class_codes("Class 2 to Class 9 Mixed-Use Development")
    assert codes == ["2", "3", "4", "5", "6", "7", "8", "9"]


def test_extract_class_codes_drops_redundant_bare_parent():
    # "Class 9" is implied by "Class 9a", so it should not be listed twice.
    codes = bc.extract_class_codes("Class 9 Buildings - Class 9a Hospitals")
    assert codes == ["9a"]


def test_extract_class_codes_ignores_out_of_range_numbers():
    assert bc.extract_class_codes("Class 42 Spaceport") == []


def test_normalise_class_code():
    assert bc.normalise_class_code("Class 9B") == "9b"
    assert bc.normalise_class_code(" 10a ") == "10a"
    assert bc.normalise_class_code("nonsense") == ""


def test_primary_class_prefers_the_lowest_code():
    assert bc.primary_class(["2", "5"]) == "2"
    assert bc.primary_class([]) == "unclassified"


# --------------------------------------------------------------------------
# NCC volume routing
# --------------------------------------------------------------------------


def test_class_1_and_10_route_to_volume_two():
    assert "Vol 2" in bc.ncc_volume_for_classes(["1a"])
    assert "Vol 2" in bc.ncc_volume_for_classes(["10a"])


def test_class_2_to_9_route_to_volume_one():
    assert "Vol 1" in bc.ncc_volume_for_classes(["9b"])
    assert "Vol 1" in bc.ncc_volume_for_classes(["5"])


def test_mixed_classes_route_to_volume_one():
    volume = bc.ncc_volume_for_classes(["1a", "2"])
    assert "Vol 1" in volume


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------


SAMPLE_RAW = {
    "building_type": "Class 1a Single Dwelling Residential",
    "structural_systems": ["Timber Framing (AS 1684)"],
    "construction_stages": [
        {
            "stage_number": 1,
            "stage_name": "Slab & Footings",
            "trades": ["Concreter"],
            "insulation_elements": [
                {
                    "element": "Under-slab insulation",
                    "material": "XPS board",
                    "placement": "Beneath slab perimeter",
                    "ncc_clause": "NCC 2022 Vol 2 Part 13.2.6",
                    "unexpected_key": "keep me",
                }
            ],
        }
    ],
}


def test_normalise_profile_extracts_codes_and_volume():
    profile = bc.normalise_profile(SAMPLE_RAW, 0)
    assert profile.class_codes == ["1a"]
    assert "Vol 2" in profile.ncc_volume
    assert len(profile.stages) == 1
    assert profile.stages[0].stage_name == "Slab & Footings"


def test_normalise_profile_accepts_singular_structural_system_key():
    raw = dict(SAMPLE_RAW)
    raw.pop("structural_systems")
    raw["structural_system"] = "Steel Framing (AS 4100)"
    profile = bc.normalise_profile(raw, 0)
    assert profile.structural_systems == ["Steel Framing (AS 4100)"]


def test_normalise_element_preserves_unknown_keys_in_extra():
    element = bc.normalise_element(SAMPLE_RAW["construction_stages"][0]["insulation_elements"][0])
    assert element.element == "Under-slab insulation"
    assert element.extra["unexpected_key"] == "keep me"


def test_profile_ids_are_unique_for_duplicate_building_types():
    a = bc.normalise_profile(SAMPLE_RAW, 0)
    b = bc.normalise_profile(SAMPLE_RAW, 1)
    assert a.profile_id != b.profile_id


# --------------------------------------------------------------------------
# SQLite ingestion
# --------------------------------------------------------------------------


@pytest.fixture()
def ingested(tmp_path):
    db_path = tmp_path / "bc.db"
    profiles = [bc.normalise_profile(SAMPLE_RAW, 0)]
    bc.ingest_profiles(profiles, db_path=db_path)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    yield connection, db_path, profiles
    connection.close()


def test_ingest_populates_all_tables(ingested):
    connection, _, _ = ingested
    counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "building_class_profiles",
            "building_class_stages",
            "building_class_elements",
            "building_class_codes",
        )
    }
    assert counts == {
        "building_class_profiles": 1,
        "building_class_stages": 1,
        "building_class_elements": 1,
        "building_class_codes": 1,
    }


def test_ingest_populates_the_fts_index(ingested):
    connection, _, _ = ingested
    assert connection.execute("SELECT COUNT(*) FROM building_class_search").fetchone()[0] == 1


def test_ingest_is_idempotent(ingested):
    connection, db_path, profiles = ingested
    bc.ingest_profiles(profiles, db_path=db_path)
    assert connection.execute("SELECT COUNT(*) FROM building_class_profiles").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM building_class_elements").fetchone()[0] == 1


def test_extra_keys_round_trip_through_sqlite(ingested):
    connection, _, _ = ingested
    extra = connection.execute("SELECT extra_json FROM building_class_elements").fetchone()[0]
    assert json.loads(extra)["unexpected_key"] == "keep me"


# --------------------------------------------------------------------------
# Query API
# --------------------------------------------------------------------------


def test_profiles_for_class_exact_subclass(ingested):
    connection, _, _ = ingested
    found = bc.profiles_for_class(connection, "1a")
    assert len(found) == 1
    assert found[0]["building_type"] == SAMPLE_RAW["building_type"]


def test_bare_parent_class_matches_subclasses(ingested):
    connection, _, _ = ingested
    assert len(bc.profiles_for_class(connection, "1")) == 1


def test_profiles_for_class_rejects_junk(ingested):
    connection, _, _ = ingested
    assert bc.profiles_for_class(connection, "not-a-class") == []


def test_unrelated_class_returns_nothing(ingested):
    connection, _, _ = ingested
    assert bc.profiles_for_class(connection, "9b") == []


def test_stages_for_profile(ingested):
    connection, _, profiles = ingested
    stages = bc.stages_for_profile(connection, profiles[0].profile_id)
    assert len(stages) == 1
    assert stages[0]["insulation_elements"][0]["element"] == "Under-slab insulation"


def test_search_elements_uses_full_text_index(ingested):
    connection, _, _ = ingested
    hits = bc.search_elements(connection, "slab")
    assert hits and "slab" in hits[0]["element"].lower()


def test_search_elements_tolerates_fts_punctuation(ingested):
    connection, _, _ = ingested
    # Must not raise an fts5 syntax error.
    assert bc.search_elements(connection, 'under-slab "insulation"') is not None


def test_class_summary(ingested):
    connection, _, _ = ingested
    summary = {row["class_code"]: row for row in bc.class_summary(connection)}
    assert summary["1a"]["profiles"] == 1
    assert summary["1a"]["elements"] == 1


# --------------------------------------------------------------------------
# Training artifacts
# --------------------------------------------------------------------------


def test_rag_chunks_have_an_overview_and_a_stage_chunk():
    chunks = bc.build_rag_chunks([bc.normalise_profile(SAMPLE_RAW, 0)])
    kinds = {chunk["kind"] for chunk in chunks}
    assert {"overview", "construction_stage"} <= kinds


def test_rag_chunk_ids_are_unique():
    profiles = [bc.normalise_profile(SAMPLE_RAW, 0), bc.normalise_profile(SAMPLE_RAW, 1)]
    ids = [chunk["chunk_id"] for chunk in bc.build_rag_chunks(profiles)]
    assert len(ids) == len(set(ids))


def test_rag_chunk_text_mentions_the_ncc_clause():
    chunks = bc.build_rag_chunks([bc.normalise_profile(SAMPLE_RAW, 0)])
    stage = next(c for c in chunks if c["kind"] == "construction_stage")
    assert "13.2.6" in stage["text"]


def test_finetune_pairs_use_the_chat_message_format():
    pairs = bc.build_finetune_pairs([bc.normalise_profile(SAMPLE_RAW, 0)])
    assert pairs
    roles = [message["role"] for message in pairs[0]["messages"]]
    assert roles == ["system", "user", "assistant"]


def test_finetune_answers_are_not_empty():
    pairs = bc.build_finetune_pairs([bc.normalise_profile(SAMPLE_RAW, 0)])
    assert all(pair["messages"][-1]["content"].strip() for pair in pairs)


def test_export_training_data_writes_both_jsonl_files(tmp_path):
    profiles = [bc.normalise_profile(SAMPLE_RAW, 0)]
    report = bc.export_training_data(profiles, out_dir=tmp_path)
    for key in ("rag_chunks_jsonl", "finetune_jsonl"):
        path = report["paths"][key]
        assert path.exists()
        for line in path.read_text(encoding="utf-8").splitlines():
            json.loads(line)
    assert json.loads(report["paths"]["report_json"].read_text(encoding="utf-8"))


def test_export_profiles_json_round_trips(tmp_path):
    profiles = [bc.normalise_profile(SAMPLE_RAW, 0)]
    path = tmp_path / "profiles.json"
    bc.export_profiles_json(profiles, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["profiles"][0]["building_type"] == SAMPLE_RAW["building_type"]
