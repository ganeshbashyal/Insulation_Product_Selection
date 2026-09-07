"""Widget config endpoint for client-side branding injection.

Serves per-site configuration to embedded widget JS so it can render
site-specific branding, contact info, colors, etc.
"""
from __future__ import annotations

from site_config import load_all_sites, SiteConfigError


class WidgetConfigProvider:
    """Provides widget configuration for client-side injection."""

    def __init__(self):
        self.sites = {}
        self._reload_sites()

    def _reload_sites(self) -> None:
        """Load all site configs."""
        try:
            self.sites = load_all_sites()
        except SiteConfigError as e:
            print(f"Warning: Failed to load site configs: {e}")

    def get_widget_config(self, site_id: str) -> dict | None:
        """
        Get widget configuration for a site.
        Returns None if site not found.

        Includes: display_name, colours, logo_url, greeting, contact info, consent text.
        Excludes: api_key, internal rate_limit, allowed_origins (security).
        """
        if site_id not in self.sites:
            return None

        site = self.sites[site_id]

        return {
            "site_id": site_id,
            "display_name": site.display_name,
            "colours": site.colours,
            "logo_url": site.logo_url,
            "greeting": site.greeting,
            "contact_method": site.contact_method,
            "phone": site.phone,
            "email": site.email,
            "callback_hours": site.callback_hours,
            "callback_wording": site.callback_wording,
            "privacy_text": site.privacy_text,
            "consent_text": site.consent_text,
        }
