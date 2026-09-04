from scripts.validate_aircall_pack import validate


def test_aircall_pack_is_current_and_safely_gated():
    assert validate() == []
