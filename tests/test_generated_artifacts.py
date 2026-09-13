from scripts.check_generated_artifacts import check


def test_checked_in_generated_artifacts_match_sources():
    assert check() == []
