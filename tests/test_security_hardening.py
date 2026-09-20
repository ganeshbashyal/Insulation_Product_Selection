"""Tests for Phase 1 production-hardening of the public API surface.

Covers the four defects fixed together:
  1. A disallowed Origin was logged and then served anyway (fail-open CORS).
  2. A request with no Origin bypassed origin checks entirely.
  3. The bundled /chat harness hardcoded a site API key in shipped source.
  4. Site API keys were read only from committed JSON, with no env injection.
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

import site_config
import web_agent
from web_agent import app, startup


@pytest.fixture
def client():
    asyncio.run(startup())
    return TestClient(app)


class TestOriginEnforcement:
    """A disallowed origin must be refused, not merely served without headers."""

    def test_disallowed_origin_is_rejected(self, client):
        response = client.post(
            "/api/conversations?site_id=local",
            headers={
                "X-API-Key": "sk_local_dev_test",
                "Origin": "https://attacker.example.com",
            },
        )
        assert response.status_code == 403
        assert "Origin" in response.json()["detail"]

    def test_allowed_origin_still_succeeds(self, client):
        response = client.post(
            "/api/conversations?site_id=local",
            headers={
                "X-API-Key": "sk_local_dev_test",
                "Origin": "http://localhost:3000",
            },
        )
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"

    def test_disallowed_origin_rejected_on_widget_config(self, client):
        response = client.get(
            "/api/widget-config?site_id=local",
            headers={"Origin": "https://attacker.example.com"},
        )
        assert response.status_code == 403

    def test_missing_origin_allowed_in_development(self, client):
        """Development keeps working for curl and server-side callers."""
        assert web_agent.REQUIRE_ORIGIN is False
        response = client.post(
            "/api/conversations?site_id=local",
            headers={"X-API-Key": "sk_local_dev_test"},
        )
        assert response.status_code == 200

    def test_missing_origin_rejected_when_required(self, client, monkeypatch):
        monkeypatch.setattr(web_agent, "REQUIRE_ORIGIN", True)
        response = client.post(
            "/api/conversations?site_id=local",
            headers={"X-API-Key": "sk_local_dev_test"},
        )
        assert response.status_code == 403


class TestDemoChatHarness:
    """The /chat page must not ship a credential and must be off in production."""

    def test_no_api_key_literal_in_shipped_html(self):
        assert "sk_local_dev_test" not in web_agent.CHAT_HTML
        assert "sk_" not in web_agent.CHAT_HTML

    def test_demo_chat_served_in_development(self, client):
        response = client.get("/chat")
        assert response.status_code == 200
        # Key is injected at render time, not baked into the source template.
        assert "sk_local_dev_test" in response.text

    def test_demo_chat_disabled_returns_404(self, client, monkeypatch):
        monkeypatch.setattr(web_agent, "DEMO_CHAT_ENABLED", False)
        response = client.get("/chat")
        assert response.status_code == 404

    def test_demo_chat_unknown_site_returns_503(self, client, monkeypatch):
        monkeypatch.setattr(web_agent, "DEMO_CHAT_SITE_ID", "does_not_exist")
        response = client.get("/chat")
        assert response.status_code == 503


class TestApiKeyInjection:
    """API keys resolve from the environment ahead of committed JSON."""

    def test_env_var_name_is_derived_from_site_id(self):
        assert site_config.api_key_env_var("local") == "AURORA_SITE_API_KEY_LOCAL"
        assert site_config.api_key_env_var("acme-au") == "AURORA_SITE_API_KEY_ACME_AU"

    def test_env_injection_overrides_committed_value(self, monkeypatch):
        monkeypatch.setenv("AURORA_SITE_API_KEY_LOCAL", "sk_from_env")
        config = site_config.load_site_config("local")
        assert config.api_key == "sk_from_env"

    def test_committed_key_used_as_development_fallback(self, monkeypatch):
        monkeypatch.delenv("AURORA_SITE_API_KEY_LOCAL", raising=False)
        config = site_config.load_site_config("local")
        assert config.api_key == "sk_local_dev_test"

    def test_committed_key_refused_in_production(self, monkeypatch):
        monkeypatch.setenv("AURORA_ENV", "production")
        monkeypatch.delenv("AURORA_SITE_API_KEY_LOCAL", raising=False)
        with pytest.raises(site_config.SiteConfigError, match="AURORA_ENV=production"):
            site_config.load_site_config("local")

    def test_env_injection_satisfies_production(self, monkeypatch):
        monkeypatch.setenv("AURORA_ENV", "production")
        monkeypatch.setenv("AURORA_SITE_API_KEY_LOCAL", "sk_prod_injected")
        config = site_config.load_site_config("local")
        assert config.api_key == "sk_prod_injected"


class TestCredentialComparison:
    """An unconfigured site must never be authenticatable."""

    def test_site_without_key_is_never_matched(self):
        from auth_middleware import AuthMiddleware

        middleware = AuthMiddleware()
        for config in middleware.sites.values():
            config.api_key = ""

        error, site = middleware.validate_api_key("anything")
        assert error == "Invalid API key"
        assert site is None
