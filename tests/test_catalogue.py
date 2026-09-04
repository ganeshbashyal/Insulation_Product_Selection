from scripts.validate_catalogue import validate


def test_catalogue_and_evidence_are_valid():
    assert validate() == []
