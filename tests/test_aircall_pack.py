from scripts.build_aircall_pack import source_hash
from scripts.validate_aircall_pack import validate


def test_aircall_pack_is_current_and_safely_gated():
    assert validate() == []


def test_aircall_source_hash_is_independent_of_text_line_endings(tmp_path):
    lf = tmp_path / "lf" / "source.json"
    crlf = tmp_path / "crlf" / "source.json"
    lf.parent.mkdir()
    crlf.parent.mkdir()
    lf.write_bytes(b'{"name":"Example"}\n')
    crlf.write_bytes(b'{"name":"Example"}\r\n')

    assert source_hash([lf]) == source_hash([crlf])
