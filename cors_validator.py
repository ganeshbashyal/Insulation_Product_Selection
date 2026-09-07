"""CORS validation for multi-site deployment.

Per-site origin allowlists configured in site_config. Validates incoming
Origin headers and rejects cross-origin requests from unauthorized origins.
"""
from __future__ import annotations

from site_config import load_all_sites, SiteConfigError


class CORSValidator:
    """Validates CORS requests against per-site allowlists."""

    def __init__(self):
        self.sites = {}
        self._reload_sites()

    def _reload_sites(self) -> None:
        """Load all site configs."""
        try:
            self.sites = load_all_sites()
        except SiteConfigError as e:
            print(f"Warning: Failed to load site configs: {e}")

    def is_origin_allowed(self, site_id: str, origin: str) -> bool:
        """
        Check if origin is allowed for site_id.
        Returns True if origin is in the site's allowed_origins list.
        """
        if site_id not in self.sites:
            return False

        site = self.sites[site_id]
        return origin in site.allowed_origins

    def get_cors_headers(self, site_id: str, origin: str) -> dict[str, str]:
        """
        Get CORS response headers if origin is allowed.
        Returns empty dict if origin is not allowed.
        """
        if not self.is_origin_allowed(site_id, origin):
            return {}

        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, X-API-Key",
            "Access-Control-Max-Age": "3600",
        }
