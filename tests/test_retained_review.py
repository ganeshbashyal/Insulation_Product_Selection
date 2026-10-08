import pytest

from retained_review import validate_decision


@pytest.mark.parametrize("decision", ["retained_confirmed", "needs_information", "rejected"])
def test_named_retained_decisions(decision):
    assert validate_decision(decision, "Checked against surviving supplied records.") == decision


@pytest.mark.parametrize("decision", ["approved", "published", "", None, True, []])
def test_no_public_approval_decision(decision):
    with pytest.raises(ValueError):
        validate_decision(decision, "Checked against surviving supplied records.")


@pytest.mark.parametrize("rationale", ["", "short", None, 42, " " * 30, "a" * 10001])
def test_explicit_bounded_rationale(rationale):
    with pytest.raises(ValueError):
        validate_decision("retained_confirmed", rationale)
