import json
from pathlib import Path

from bot_engine import rank_families, recommendation_allowed, technical_gate

ROOT = Path(__file__).resolve().parents[1]


def catalogue():
    families = []
    for manufacturer in ("thermotec", "fletcher"):
        document = json.loads((ROOT / "knowledge" / manufacturer / "families.json").read_text(encoding="utf-8"))
        for family in document["families"]:
            family["manufacturer"] = manufacturer.title()
            families.append(family)
    return families


def top(answers, scope=None):
    return rank_families(catalogue(), answers, scope)[0]


def test_thermal_wall_does_not_select_acoustic_batt():
    result = top({"challenge": "Rooms are hot and cold", "application": "external wall", "priority": "thermal energy savings"})
    assert result["family_id"] == "FLETCHER_PINK_BATTS_WALL"


def test_roof_ceiling_placement_is_respected():
    result = top({"challenge": "thermal comfort", "application": "at ceiling level below the roof space", "priority": "energy efficiency"})
    assert result["family_id"] == "FLETCHER_PINK_BATTS_CEILING"


def test_between_floor_paraphrase_and_typo_select_soundbreak():
    result = top({"challenge": "nois between stories", "application": "interfloor cavity", "priority": "acoustic comfort"})
    assert result["family_id"] == "FLETCHER_SOUNDBREAK"


def test_underlay_misspelling_selects_underlay():
    result = top({"challenge": "soundproffing footsteps", "application": "under the carpett", "priority": "quiet"}, "Thermotec")
    assert result["family_id"] == "THERMOTEC_NUWAVE_UNDERLAY"


def test_unverified_identity_is_never_recommendable():
    family = {"confidence": "manufacturer_supported_identity_review"}
    assert recommendation_allowed(family) is False
    assert technical_gate({}, family)[0] == "BLOCKED"


def test_secondary_source_family_is_never_recommendable():
    assert recommendation_allowed({"confidence": "secondary_owned_source_only"}) is False
    assert recommendation_allowed({"confidence": "identity_unverified"}) is False


def test_no_reliable_match_for_unrelated_enquiry():
    result = top({"challenge": "I need something for my garden fountain", "application": "unknown", "priority": "budget"})
    assert result["reliable_match"] is False
    assert technical_gate({}, result)[0] == "BLOCKED"


def test_singularisation_exception_keeps_services_intact():
    result = top({"challenge": "noise breakout", "application": "building services waste pipe", "priority": "acoustic comfort"}, "Thermotec")
    assert result["family_id"] in {"THERMOTEC_NUWRAP_5", "THERMOTEC_NUWRAP_XTRAFLEX"}
    assert result["reliable_match"] is True
