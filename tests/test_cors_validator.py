"""Tests for CORS validation."""
import pytest

from cors_validator import CORSValidator


@pytest.fixture
def cors_validator():
    """Create a CORSValidator instance."""
    return CORSValidator()


def test_allowed_origin(cors_validator):
    """Check if allowed origin is recognized."""
    allowed = cors_validator.is_origin_allowed("acme", "https://acme.example.com")
    assert allowed


def test_disallowed_origin(cors_validator):
    """Check if disallowed origin is rejected."""
    allowed = cors_validator.is_origin_allowed("acme", "https://attacker.example.com")
    assert not allowed


def test_empty_origin_string(cors_validator):
    """Empty origin is rejected."""
    allowed = cors_validator.is_origin_allowed("acme", "")
    assert not allowed


def test_invalid_site(cors_validator):
    """Check invalid site_id returns False."""
    allowed = cors_validator.is_origin_allowed("nonexistent", "https://example.com")
    assert not allowed


def test_get_cors_headers_allowed(cors_validator):
    """Get CORS headers for allowed origin."""
    headers = cors_validator.get_cors_headers("acme", "https://acme.example.com")
    assert headers["Access-Control-Allow-Origin"] == "https://acme.example.com"
    assert "Access-Control-Allow-Methods" in headers
    assert "Access-Control-Allow-Headers" in headers


def test_get_cors_headers_disallowed(cors_validator):
    """Get CORS headers for disallowed origin returns empty."""
    headers = cors_validator.get_cors_headers("acme", "https://attacker.example.com")
    assert headers == {}


def test_cors_headers_include_x_api_key(cors_validator):
    """CORS headers include X-API-Key in allowed headers."""
    headers = cors_validator.get_cors_headers("acme", "https://acme.example.com")
    assert "X-API-Key" in headers["Access-Control-Allow-Headers"]


def test_multiple_allowed_origins(cors_validator):
    """Both allowed origins are recognized."""
    assert cors_validator.is_origin_allowed("acme", "https://acme.example.com")
    assert cors_validator.is_origin_allowed("acme", "https://www.acme.example.com")


def test_local_site_localhost(cors_validator):
    """Local site allows localhost origins."""
    allowed = cors_validator.is_origin_allowed("local", "http://localhost:3000")
    assert allowed


def test_local_site_127(cors_validator):
    """Local site allows 127.0.0.1."""
    allowed = cors_validator.is_origin_allowed("local", "http://127.0.0.1:3000")
    assert allowed
