"""API authentication middleware for multi-site deployment.

Validates API keys per site, enforces rate limiting, and audit logs auth events.
"""
from __future__ import annotations

import json
import hmac
import os
import sqlite3
import time
import uuid
from abc import ABC, abstractmethod
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from site_config import SiteConfig, load_all_sites, SiteConfigError

ROOT = Path(__file__).resolve().parent
DEFAULT_AUDIT_DB = ROOT / "data" / "local" / "audit.sqlite3"
DEFAULT_RATE_LIMIT_DB = ROOT / "data" / "local" / "rate_limits.sqlite3"


class RateLimiter(ABC):
    """Abstract rate limiter."""

    @abstractmethod
    def is_allowed(self, key: str, limit: int) -> bool:
        """Check if an action is allowed. Key is usually (site_id, ip_address)."""
        pass


class InMemoryRateLimiter(RateLimiter):
    """
    Simple in-memory rate limiter (per-minute window).

    Single-process only. Each worker keeps its own counters, so N workers grant
    N times the configured quota. Safe for tests and single-worker development;
    use SQLiteRateLimiter or RedisRateLimiter for anything served by more than
    one process.
    """

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


class SQLiteRateLimiter(RateLimiter):
    """
    Sliding-window rate limiter shared across every process on one host.

    This is the default because it makes `uvicorn --workers N` correct without
    introducing any new infrastructure: SQLite in WAL mode already coordinates
    concurrent writers. The check and the increment run inside a single
    BEGIN IMMEDIATE transaction, so two workers cannot both observe "under the
    limit" and both admit a request.

    It coordinates processes on one machine only. Across multiple hosts each
    machine keeps its own counters, so use RedisRateLimiter there.
    """

    def __init__(self, db_path: Path | None = None, window_seconds: int = 60):
        self.db_path = db_path or DEFAULT_RATE_LIMIT_DB
        self.window_seconds = window_seconds
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        # isolation_level=None disables the driver's implicit transaction
        # handling so the explicit BEGIN IMMEDIATE below is the real one.
        conn = sqlite3.connect(self.db_path, timeout=5.0, isolation_level=None)
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rate_limit_hits (
                    bucket_key TEXT NOT NULL,
                    hit_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rate_limit_hits ON rate_limit_hits (bucket_key, hit_at)"
            )
        finally:
            conn.close()

    def is_allowed(self, key: str, limit: int) -> bool:
        try:
            return self._check_and_record(key, limit)
        except sqlite3.OperationalError as e:
            # The backing file can disappear underneath a long-lived worker
            # (rotation, cleanup, an operator clearing state). Recreate the
            # schema and retry once rather than failing every subsequent
            # request, which would take the whole API down for a recoverable
            # storage problem.
            if "no such table" not in str(e).casefold():
                raise
            print("Warning: rate limit store missing, recreating schema")
            self._init_db()
            return self._check_and_record(key, limit)

    def _check_and_record(self, key: str, limit: int) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("DELETE FROM rate_limit_hits WHERE hit_at < ?", (cutoff,))
                count = conn.execute(
                    "SELECT COUNT(*) FROM rate_limit_hits WHERE bucket_key = ? AND hit_at >= ?",
                    (key, cutoff),
                ).fetchone()[0]

                if count >= limit:
                    conn.execute("COMMIT")
                    return False

                conn.execute(
                    "INSERT INTO rate_limit_hits (bucket_key, hit_at) VALUES (?, ?)",
                    (key, now),
                )
                conn.execute("COMMIT")
                return True
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()


class RedisRateLimiter(RateLimiter):
    """
    Sliding-window rate limiter shared across hosts.

    Uses a sorted set per bucket, trimmed to the window on every call. The
    trim/count/insert sequence runs as a single Lua script so it is atomic
    across replicas - a pipeline would leave a window in which two replicas
    both read a count below the limit.

    Fails closed: if Redis is unreachable the request is denied rather than
    silently granted, so an outage cannot become an unmetered open door.
    """

    _SCRIPT = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local limit = tonumber(ARGV[3])
    local member = ARGV[4]

    redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
    local count = redis.call('ZCARD', key)
    if count >= limit then
        return 0
    end
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, math.ceil(window))
    return 1
    """

    def __init__(self, client: Any, window_seconds: int = 60, namespace: str = "aurora:rl:"):
        self.client = client
        self.window_seconds = window_seconds
        self.namespace = namespace
        self._script = client.register_script(self._SCRIPT)

    def is_allowed(self, key: str, limit: int) -> bool:
        now = time.time()
        member = f"{now:.6f}:{uuid.uuid4().hex}"
        try:
            allowed = self._script(
                keys=[f"{self.namespace}{key}"],
                args=[now, self.window_seconds, limit, member],
            )
        except Exception as e:
            print(f"Warning: rate limiter backend unavailable, denying request: {e}")
            return False
        return bool(allowed)


def build_rate_limiter(backend: str | None = None) -> RateLimiter:
    """
    Construct the configured rate limiter.

    AURORA_RATE_LIMIT_BACKEND selects the implementation:
      sqlite (default) - correct across workers on one host, no extra services
      redis            - correct across hosts, requires a reachable Redis
      memory           - single process only, for tests and development

    The default is deliberately sqlite rather than memory: the in-memory
    limiter silently multiplies the configured quota by the worker count, and
    that failure is invisible in testing because a single-worker dev server
    behaves correctly.
    """
    choice = (backend or os.getenv("AURORA_RATE_LIMIT_BACKEND", "sqlite")).strip().casefold()

    if choice == "memory":
        return InMemoryRateLimiter()
    if choice == "sqlite":
        return SQLiteRateLimiter()
    if choice == "redis":
        import redis_support

        return RedisRateLimiter(redis_support.get_client())

    raise ValueError(
        f"Unknown AURORA_RATE_LIMIT_BACKEND '{choice}'. Expected sqlite, redis or memory."
    )


class AuditLog:

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
        # Defaults to the configured shared-state limiter rather than the
        # in-memory one, so a deployment that forgets to inject a limiter is
        # still correct across workers instead of quietly multiplying quotas.
        self.rate_limiter = rate_limiter or build_rate_limiter()
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

        # Constant-time comparison, and sites with no configured key can never
        # be matched - otherwise an unconfigured site would be authenticated by
        # any caller that happened to send a blank-equivalent value.
        for site_id, config in self.sites.items():
            if not config.api_key:
                continue
            if hmac.compare_digest(config.api_key, api_key):
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
