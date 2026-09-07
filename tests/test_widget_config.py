"""Tests for widget configuration provider."""
import pytest

from widget_config import WidgetConfigProvider


@pytest.fixture
def widget_provider():
    """Create a WidgetConfigProvider instance."""
    return WidgetConfigProvider()


def test_get_acme_config(widget_provider):
    """Get widget config for acme site."""
    config = widget_provider.get_widget_config("acme")
    assert config is not None
    assert config["site_id"] == "acme"
    assert config["display_name"] == "ACME Construction"
    assert "primary" in config["colours"]
    assert "accent" in config["colours"]
    assert config["contact_method"] == "callback"
    assert config["callback_hours"] == "Mon–Fri 8am–5pm AEDT"


def test_get_local_config(widget_provider):
    """Get widget config for local site."""
    config = widget_provider.get_widget_config("local")
    assert config is not None
    assert config["site_id"] == "local"
    assert config["contact_method"] == "phone"
    assert config["phone"] == "+61-2-9000-0000"


def test_nonexistent_site(widget_provider):
    """Get config for nonexistent site returns None."""
    config = widget_provider.get_widget_config("nonexistent")
    assert config is None


def test_config_excludes_sensitive_fields(widget_provider):
    """Widget config excludes api_key, rate_limit, allowed_origins."""
    config = widget_provider.get_widget_config("acme")
    assert "api_key" not in config
    assert "rate_limit" not in config
    assert "allowed_origins" not in config
    assert "manufacturer_emphasis" not in config


def test_config_includes_branding(widget_provider):
    """Widget config includes all branding fields."""
    config = widget_provider.get_widget_config("acme")
    required_fields = [
        "site_id",
        "display_name",
        "colours",
        "logo_url",
        "greeting",
        "privacy_text",
        "consent_text",
    ]
    for field in required_fields:
        assert field in config, f"Missing field: {field}"


def test_config_is_json_serializable(widget_provider):
    """Widget config is JSON-serializable."""
    import json
    config = widget_provider.get_widget_config("acme")
    # Should not raise
    json.dumps(config)


def test_config_contact_info_present(widget_provider):
    """Widget config includes contact info for all methods."""
    acme = widget_provider.get_widget_config("acme")
    assert acme["contact_method"] == "callback"
    assert acme["callback_hours"] is not None
    assert acme["callback_wording"] is not None

    local = widget_provider.get_widget_config("local")
    assert local["contact_method"] == "phone"
    assert local["phone"] is not None


def test_greeting_included(widget_provider):
    """Widget config includes personalized greeting."""
    config = widget_provider.get_widget_config("acme")
    assert config["greeting"]
    assert "ACME" in config["greeting"]


def test_colours_have_primary_and_accent(widget_provider):
    """Widget config colours include primary and accent."""
    config = widget_provider.get_widget_config("acme")
    colours = config["colours"]
    assert "primary" in colours
    assert "accent" in colours
    assert colours["primary"]
    assert colours["accent"]
