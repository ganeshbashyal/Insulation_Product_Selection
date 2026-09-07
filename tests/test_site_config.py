"""Tests for site configuration loader."""
import json
from pathlib import Path

import pytest

from site_config import SiteConfig, SiteConfigError, load_all_sites, load_site_config


def test_load_acme_config():
    """Verify acme config loads and validates."""
    config = load_site_config("acme")
    assert config.site_id == "acme"
    assert config.display_name == "ACME Construction"
    assert config.contact_method == "callback"
    assert config.callback_hours == "Mon–Fri 8am–5pm AEDT"
    assert "https://acme.example.com" in config.allowed_origins
    assert len(config.allowed_origins) == 2


def test_load_local_config():
    """Verify local config loads and validates."""
    config = load_site_config("local")
    assert config.site_id == "local"
    assert config.contact_method == "phone"
    assert config.phone == "+61-2-9000-0000"
    assert "http://localhost:3000" in config.allowed_origins


def test_load_all_sites():
    """Verify all configs load together."""
    sites = load_all_sites()
    assert "acme" in sites
    assert "local" in sites
    assert len(sites) >= 2


def test_missing_required_field():
    """Config without required field raises SiteConfigError."""
    with pytest.raises(SiteConfigError, match="Missing required fields"):
        from site_config import _validate_and_build
        _validate_and_build({
            "site_id": "bad",
            "display_name": "Bad Config",
            # missing colours, logo_url, etc.
        })


def test_invalid_contact_method():
    """Invalid contact_method raises error."""
    with pytest.raises(SiteConfigError, match="Invalid contact_method"):
        from site_config import _validate_and_build
        _validate_and_build({
            "site_id": "bad",
            "display_name": "Bad",
            "colours": {"primary": "#000", "accent": "#fff"},
            "logo_url": "http://logo.png",
            "greeting": "hi",
            "contact_method": "invalid",
            "allowed_origins": ["http://localhost"],
        })


def test_phone_contact_requires_phone():
    """contact_method='phone' without phone field raises error."""
    with pytest.raises(SiteConfigError, match="requires 'phone' field"):
        from site_config import _validate_and_build
        _validate_and_build({
            "site_id": "bad",
            "display_name": "Bad",
            "colours": {"primary": "#000", "accent": "#fff"},
            "logo_url": "http://logo.png",
            "greeting": "hi",
            "contact_method": "phone",
            "allowed_origins": ["http://localhost"],
        })


def test_callback_contact_requires_callback_hours():
    """contact_method='callback' without callback_hours raises error."""
    with pytest.raises(SiteConfigError, match="requires 'callback_hours' field"):
        from site_config import _validate_and_build
        _validate_and_build({
            "site_id": "bad",
            "display_name": "Bad",
            "colours": {"primary": "#000", "accent": "#fff"},
            "logo_url": "http://logo.png",
            "greeting": "hi",
            "contact_method": "callback",
            "allowed_origins": ["http://localhost"],
        })


def test_missing_colours():
    """Missing primary or accent colour raises error."""
    with pytest.raises(SiteConfigError, match="colours must have"):
        from site_config import _validate_and_build
        _validate_and_build({
            "site_id": "bad",
            "display_name": "Bad",
            "colours": {"primary": "#000"},  # missing accent
            "logo_url": "http://logo.png",
            "greeting": "hi",
            "contact_method": "phone",
            "phone": "+61-2-9000-0000",
            "allowed_origins": ["http://localhost"],
        })


def test_empty_allowed_origins():
    """Empty allowed_origins list raises error."""
    with pytest.raises(SiteConfigError, match="allowed_origins must be a non-empty list"):
        from site_config import _validate_and_build
        _validate_and_build({
            "site_id": "bad",
            "display_name": "Bad",
            "colours": {"primary": "#000", "accent": "#fff"},
            "logo_url": "http://logo.png",
            "greeting": "hi",
            "contact_method": "phone",
            "phone": "+61-2-9000-0000",
            "allowed_origins": [],
        })


def test_config_to_dict():
    """SiteConfig.to_dict() produces safe JSON."""
    config = load_site_config("acme")
    d = config.to_dict()
    # Verify it's JSON-serializable
    json_str = json.dumps(d)
    assert "acme" in json_str
    assert "ACME" in json_str
