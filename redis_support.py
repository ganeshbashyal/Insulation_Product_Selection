"""Optional Redis connectivity for multi-host deployments.

Redis is not required. A single host running `uvicorn --workers N` is fully
served by the SQLite-backed stores, which coordinate processes through WAL. This
module exists for the point at which the API is served from more than one
machine and those processes must share state.

The redis package is imported lazily so the application still starts, and the
whole test suite still runs, on a machine with no Redis installed.
"""
from __future__ import annotations

import os
from typing import Any

DEFAULT_URL = "redis://127.0.0.1:6379/0"


class RedisUnavailable(RuntimeError):
    """Raised when a Redis backend is requested but cannot be reached."""


def redis_url() -> str:
    """Configured Redis URL (AURORA_REDIS_URL), defaulting to a local server."""
    return os.getenv("AURORA_REDIS_URL", DEFAULT_URL)


def get_client(url: str | None = None) -> Any:
    """
    Build and verify a Redis client.

    Raises RedisUnavailable rather than returning a lazily-broken client, so a
    misconfigured deployment fails at startup instead of at the first request.
    """
    try:
        import redis
    except ImportError as e:
        raise RedisUnavailable(
            "The 'redis' package is required for Redis-backed stores. "
            "Install it with: pip install redis"
        ) from e

    target = url or redis_url()
    try:
        client = redis.Redis.from_url(target, decode_responses=True)
        client.ping()
    except Exception as e:
        raise RedisUnavailable(f"Could not reach Redis at {target}: {e}") from e

    return client


def is_available(url: str | None = None) -> bool:
    """True when a Redis server is reachable. Used to skip optional tests."""
    try:
        get_client(url)
        return True
    except RedisUnavailable:
        return False
