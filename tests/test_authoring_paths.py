"""Local Llama draft, reviewed against the private authoring allowlist."""
import pytest

from authoring_backup import permitted


@pytest.mark.parametrize("name", [
    "knowledge/test/research/legacy.json", "data/tds/shared.pdf", "reports/manual.xlsx",
    "data/local/intake/receipt.json", "data/local/product_research.sqlite3",
])
def test_valid_paths(name):
    assert permitted(name)


@pytest.mark.parametrize("name", [
    "../knowledge/a", "knowledge/../a", "knowledge//a", "data/local/sessions.sqlite3",
    "config/sites/site.json", "C:/knowledge/a",
])
def test_invalid_paths(name):
    assert not permitted(name)
