"""Rules that keep polluted retrieval terms out of ranking and retrieval cards."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from retrieval_hygiene import clean_term, clean_terms, clean_retrieval, ranker_safe_terms


def test_line_wrap_artifacts_are_salvaged_not_dropped():
    assert clean_term("Foilboard garage kit\ndouble", "search_keywords") == "Foilboard garage kit double"
    assert clean_term("10mm drainage\n    strip", "search_keywords") == "10mm drainage strip"


def test_label_bleed_is_dropped():
    assert clean_term("- Negative Filter (not_for): Not for top-of-wall roof junctions (use Party", "problem_keywords") is None
    assert clean_term("- Positive Recommendation Rule: Use for fixing 10mm Foilboard", "use_cases") is None
    assert clean_term("- Placement: Wall, external wall, shed.", "problem_keywords") is None


def test_not_for_payload_survives_its_wrapper():
    # the wrapper is junk but the payload is the negative-match term we need
    assert clean_term("not_for): Not a structural framing batten", "not_for") == "structural framing batten"


def test_prose_sentences_are_dropped():
    assert clean_term("external wraps cause internal moisture condensation.", "not_for") is None or \
        "." not in (clean_term("external wraps cause internal moisture condensation.", "not_for") or "")
    assert clean_term(
        "When builder is installing lightweight cladding on steel/timber framing in high-rainfall zones, recommend CDB-451200. Stack two layers",
        "use_cases",
    ) is None


def test_placement_extracts_leading_element_from_glued_prose():
    assert clean_term("roofline. - Positive Recommendation Rule: When airflow circulation", "placement") == "roofline"
    assert clean_term('"roofline"', "placement") == "roofline"


def test_placement_rejects_instruction_fragments():
    assert clean_term("recommend CDB-451200", "placement") is None
    assert clean_term("s without pins", "placement") is None


def test_priority_fit_is_vocabulary_bound():
    assert clean_term("thermal", "priority_fit") == "thermal"
    assert clean_term("easy_install", "priority_fit") == "easy_install"
    assert clean_term("benchmark pipe lagging", "priority_fit") is None


def test_pipeline_artifacts_and_fragments_are_dropped():
    assert clean_term("BATCH 015", "not_for") is None
    assert clean_term("high", "problem_keywords") is None          # generic solo word
    assert clean_term("insulation subjected to loads and", "use_cases") is None  # dangling tail
    assert clean_term("customer wants a", "problem_keywords") is None


def test_uppercase_shape_descriptors_survive():
    assert clean_term("U shaped desk screen", "search_keywords") == "U shaped desk screen"


def test_truncated_paren_is_cut_not_kept():
    assert clean_term("Roof sarking under tiles or metal roofs (must use", "not_for") == \
        "Roof sarking under tiles or metal roofs"


def test_mojibake_repair():
    assert clean_term("cavity (minimum 38mm�50mm)", "not_for") == "cavity (minimum 38mm-50mm)"
    assert clean_term("Operating temperatures exceeding 75�C", "not_for") == "Operating temperatures exceeding 75°C"


def test_trailing_wrapper_junk_strips_to_stable():
    assert clean_term('board 32kg".', "problem_keywords") == "board 32kg"
    assert clean_term("Roof)", "use_cases") == "Roof"


def test_clean_terms_dedupes_case_insensitively():
    assert clean_terms(["Pink Batts", "pink batts", "pink\nbatts"], "search_keywords") == ["Pink Batts"]


def test_clean_retrieval_passes_unknown_keys_through():
    block = {"search_keywords": ["ok term", "- Placement: junk:"], "rag_summary": "keep me"}
    cleaned = clean_retrieval(block)
    assert cleaned["search_keywords"] == ["ok term"]
    assert cleaned["rag_summary"] == "keep me"


def test_ranker_safe_terms_excludes_long_scenarios():
    terms = [
        "wall batts",
        "Insulating existing timber-stud external walls during a major renovation project",
        "label: bleed",
    ]
    assert ranker_safe_terms(terms) == ["wall batts"]
