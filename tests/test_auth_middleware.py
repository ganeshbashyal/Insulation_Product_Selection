"""Tests for authentication middleware."""
import tempfile
from pathlib import Path

import pytest

from auth_middleware import (
    AuthMiddleware,
    InMemoryRateLimiter,
    AuditLog,
)
from site_config import SiteConfig


@pytest.fixture
def auth_middleware():
    """Create an AuthMiddleware instance."""
    return AuthMiddleware()


@pytest.fixture
def temp_audit_db():
    """Create a temporary audit database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "audit.sqlite3"
        yield db_path
        # Force garbage collection to close any open connections
        import gc
        gc.collect()


def test_validate_valid_api_key(auth_middleware):
    """Validate a valid API key returns the site config."""
    error, site = auth_middleware.validate_api_key("sk_acme_prod_xxxxx")
    assert error is None
    assert site is not None
    assert site.site_id == "acme"


def test_validate_invalid_api_key(auth_middleware):
    """Invalid API key returns error."""
    error, site = auth_middleware.validate_api_key("invalid_key")
    assert error == "Invalid API key"
    assert site is None


def test_validate_missing_api_key(auth_middleware):
    """Missing API key returns error."""
    error, site = auth_middleware.validate_api_key("")
    assert error == "Missing API key"
    assert site is None


def test_rate_limit_allows_under_limit():
    """Rate limiter allows requests under the limit."""
    limiter = InMemoryRateLimiter()
    assert limiter.is_allowed("site:192.168.1.1", 10)
    assert limiter.is_allowed("site:192.168.1.1", 10)
    assert limiter.is_allowed("site:192.168.1.1", 10)


def test_rate_limit_blocks_over_limit():
    """Rate limiter blocks requests over the limit."""
    limiter = InMemoryRateLimiter()
    limit = 3
    for i in range(limit):
        assert limiter.is_allowed("site:192.168.1.1", limit)
    # Next request should be blocked
    assert not limiter.is_allowed("site:192.168.1.1", limit)


def test_rate_limit_per_key():
    """Different keys have separate rate limits."""
    limiter = InMemoryRateLimiter()
    limit = 2
    # Fill up key1
    for i in range(limit):
        assert limiter.is_allowed("site:192.168.1.1", limit)
    # key1 should be blocked
    assert not limiter.is_allowed("site:192.168.1.1", limit)
    # key2 should still work
    assert limiter.is_allowed("site:192.168.1.2", limit)


def test_check_rate_limit_valid_site(auth_middleware):
    """Rate limit check on valid site."""
    is_allowed = auth_middleware.check_rate_limit("acme", "192.168.1.1")
    assert is_allowed


def test_check_rate_limit_invalid_site(auth_middleware):
    """Rate limit check on invalid site returns False."""
    is_allowed = auth_middleware.check_rate_limit("nonexistent", "192.168.1.1")
    assert not is_allowed


def test_audit_log_creates_entry(temp_audit_db):
    """Audit log creates an entry."""
    log = AuditLog(temp_audit_db)
    log.log("api_key_auth", site_id="acme", ip_address="192.168.1.1", status_code=200)

    import sqlite3
    with sqlite3.connect(temp_audit_db) as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM audit_log")
        count = cursor.fetchone()[0]
        assert count == 1


def test_audit_log_includes_details(temp_audit_db):
    """Audit log includes details dict."""
    log = AuditLog(temp_audit_db)
    log.log(
        "rate_limit_hit",
        site_id="acme",
        ip_address="192.168.1.1",
        details={"reason": "too many requests"},
        status_code=429,
    )

    import sqlite3
    import json
    with sqlite3.connect(temp_audit_db) as conn:
        cursor = conn.execute("SELECT details FROM audit_log WHERE event_type = ?", ("rate_limit_hit",))
        row = cursor.fetchone()
        assert row is not None
        details = json.loads(row[0])
        assert details["reason"] == "too many requests"
