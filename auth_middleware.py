"""API authentication middleware for multi-site deployment.

Validates API keys per site, enforces rate limiting, and audit logs auth events.
"""
from __future__ import annotations

import json
import sqlite3
import time
from abc import ABC, abstractmethod
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from site_config import SiteConfig, load_all_sites, SiteConfigError

ROOT = Path(__file__).resolve().parent
DEFAULT_AUDIT_DB = ROOT / "data" / "local" / "audit.sqlite3"


class RateLimiter(ABC):
    """Abstract rate limiter."""

    @abstractmethod
    def is_allowed(self, key: str, limit: int) -> bool:
        """Check if an action is allowed. Key is usually (site_id, ip_address)."""
        pass


class InMemoryRateLimiter(RateLimiter):
    """Simple in-memory rate limiter (per-minute window)."""

    def __init__(self):
        self.windows: dict[str, list[float]] = {}

    def is_allowed(self, key: str, limit: int) -> bool:
        """Check if key has fewer than `limit` requests in the current minute."""
        now = time.time()
        minute_ago = now - 60

        # Initialize or fetch window
        if key not in self.windows:
            self.windows[key] = []

        # Remove old entries
        self.windows[key] = [t for t in self.windows[key] if t > minute_ago]

        # Check limit
        if len(self.windows[key]) < limit:
            self.windows[key].append(now)
            return True

        return False


class AuditLog:
    """Audit logging for auth events."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DEFAULT_AUDIT_DB
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path, timeout=5.0) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    site_id TEXT,
                    event_type TEXT NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    details TEXT,
                    status_code INTEGER
                )
                """
            )
            conn.commit()

    def log(
        self,
        event_type: str,
        site_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
        status_code: int | None = None,
    ) -> None:
        """Log an auth event."""
        import datetime
        import pytz
        timestamp = datetime.datetime.now(pytz.UTC).isoformat(timespec="seconds")
        with sqlite3.connect(self.db_path, timeout=5.0) as conn:
            conn.execute(
                """
                INSERT INTO audit_log (timestamp, site_id, event_type, ip_address, user_agent, details, status_code)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    site_id,
                    event_type,
                    ip_address,
                    user_agent,
                    json.dumps(details or {}),
                    status_code,
                ),
            )
            conn.commit()


class AuthMiddleware:
    """Middleware for API key validation and rate limiting."""

    def __init__(
        self,
        rate_limiter: RateLimiter | None = None,
        audit_log: AuditLog | None = None,
    ):
        self.rate_limiter = rate_limiter or InMemoryRateLimiter()
        self.audit_log = audit_log or AuditLog()
        self.sites = {}
        self._reload_sites()

    def _reload_sites(self) -> None:
        """Load all site configs."""
        try:
            self.sites = load_all_sites()
        except SiteConfigError as e:
            print(f"Warning: Failed to load site configs: {e}")

    def validate_api_key(self, api_key: str) -> tuple[str | None, SiteConfig | None]:
        """
        Validate an API key. Returns (error_message, site_config) or (None, site_config) on success.
        """
        if not api_key:
            return "Missing API key", None

        # Find site by API key
        for site_id, config in self.sites.items():
            if config.api_key == api_key:
                return None, config

        return "Invalid API key", None

    def check_rate_limit(self, site_id: str, ip_address: str) -> bool:
        """Check if (site_id, ip_address) is within rate limit."""
        if site_id not in self.sites:
            return False

        site = self.sites[site_id]
        limit = site.rate_limit.get("requests_per_minute", 10)
        key = f"{site_id}:{ip_address}"

        return self.rate_limiter.is_allowed(key, limit)


def auth_required(f: Callable) -> Callable:
    """
    Decorator for FastAPI endpoints that require API key auth.
    Expects the endpoint to accept (request, site_id) as first positional args after self.

    Usage:
        @app.post("/api/learning/message")
        @auth_required
        async def message(request: Request, site_id: str, ...):
            ...
    """

    @wraps(f)
    async def wrapper(*args, **kwargs):
        # This is a stub; actual FastAPI integration will inject auth middleware.
        return await f(*args, **kwargs)

    wrapper.auth_required = True  # Mark for middleware
    return wrapper
