"""Site configuration loader. Validates and caches per-site branding, contact routing, and auth rules."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


@dataclass
class SiteConfig:
    """Immutable site configuration."""
    site_id: str
    display_name: str
    colours: dict[str, str]
    logo_url: str
    greeting: str
    contact_method: str  # "phone" | "email" | "callback"
    phone: str | None = None
    email: str | None = None
    callback_hours: str | None = None
    callback_wording: str | None = None
    privacy_text: str = ""
    consent_text: str = ""
    allowed_origins: list[str] = None
    api_key: str = ""
    rate_limit: dict[str, int] = None
    manufacturer_emphasis: dict[str, float] = None

    def __post_init__(self):
        if self.allowed_origins is None:
            self.allowed_origins = []
        if self.rate_limit is None:
            self.rate_limit = {"requests_per_minute": 10, "per_ip": True}
        if self.manufacturer_emphasis is None:
            self.manufacturer_emphasis = {}

    def to_dict(self) -> dict[str, Any]:
        """Export to dict, safe for JSON serialization."""
        return {
            "site_id": self.site_id,
            "display_name": self.display_name,
            "colours": self.colours,
            "logo_url": self.logo_url,
            "greeting": self.greeting,
            "contact_method": self.contact_method,
            "phone": self.phone,
            "email": self.email,
            "callback_hours": self.callback_hours,
            "callback_wording": self.callback_wording,
            "privacy_text": self.privacy_text,
            "consent_text": self.consent_text,
            "allowed_origins": self.allowed_origins,
            "rate_limit": self.rate_limit,
            "manufacturer_emphasis": self.manufacturer_emphasis,
        }


class SiteConfigError(Exception):
    """Raised on config validation failure."""
    pass


def load_site_config(site_id: str) -> SiteConfig:
    """Load and validate a site config by ID. Raises SiteConfigError if missing or invalid."""
    config_path = ROOT / "config" / "sites" / f"{site_id}.json"
    if not config_path.exists():
        raise SiteConfigError(f"Site config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return _validate_and_build(data)


def load_all_sites() -> dict[str, SiteConfig]:
    """Load all site configs from config/sites/. Returns {site_id -> SiteConfig}."""
    sites_dir = ROOT / "config" / "sites"
    sites_dir.mkdir(parents=True, exist_ok=True)

    sites: dict[str, SiteConfig] = {}
    for config_file in sorted(sites_dir.glob("*.json")):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            site = _validate_and_build(data)
            sites[site.site_id] = site
        except (json.JSONDecodeError, KeyError, SiteConfigError) as e:
            raise SiteConfigError(f"Failed to load {config_file}: {e}")

    return sites


def _validate_and_build(data: dict) -> SiteConfig:
    """Validate a config dict and build a SiteConfig. Raises SiteConfigError on failure."""
    required = {"site_id", "display_name", "colours", "logo_url", "greeting", "contact_method", "allowed_origins"}
    missing = required - set(data.keys())
    if missing:
        raise SiteConfigError(f"Missing required fields: {missing}")

    contact_method = data.get("contact_method")
    if contact_method not in {"phone", "email", "callback"}:
        raise SiteConfigError(f"Invalid contact_method: {contact_method}")

    # Validate contact details based on method
    if contact_method == "phone" and not data.get("phone"):
        raise SiteConfigError("contact_method='phone' requires 'phone' field")
    if contact_method == "email" and not data.get("email"):
        raise SiteConfigError("contact_method='email' requires 'email' field")
    if contact_method == "callback" and not data.get("callback_hours"):
        raise SiteConfigError("contact_method='callback' requires 'callback_hours' field")

    # Validate colours dict
    colours = data.get("colours", {})
    if not isinstance(colours, dict) or not colours.get("primary") or not colours.get("accent"):
        raise SiteConfigError("colours must have 'primary' and 'accent' keys")

    # Validate allowed_origins is non-empty list
    origins = data.get("allowed_origins", [])
    if not isinstance(origins, list) or not origins:
        raise SiteConfigError("allowed_origins must be a non-empty list")

    # Build the config object
    return SiteConfig(
        site_id=data["site_id"],
        display_name=data["display_name"],
        colours=colours,
        logo_url=data["logo_url"],
        greeting=data["greeting"],
        contact_method=contact_method,
        phone=data.get("phone"),
        email=data.get("email"),
        callback_hours=data.get("callback_hours"),
        callback_wording=data.get("callback_wording"),
        privacy_text=data.get("privacy_text", ""),
        consent_text=data.get("consent_text", ""),
        allowed_origins=origins,
        api_key=data.get("api_key", ""),
        rate_limit=data.get("rate_limit", {"requests_per_minute": 10, "per_ip": True}),
        manufacturer_emphasis=data.get("manufacturer_emphasis", {}),
    )
