"""Session storage for multi-worker, persistent conversation sessions.

Replaces the in-process _SESSIONS dict in web_agent.py. Supports SQLite (default)
or Redis backend. Sessions are scoped by site_id and expire after TTL (24h from
last access).
"""
from __future__ import annotations

import json
import os
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from local_db import connect

DEFAULT_DB = Path(__file__).resolve().parent / "data" / "local" / "sessions.sqlite3"


class Session:
    """Immutable session record."""
    def __init__(
        self,
        session_id: str,
        site_id: str,
        conversation_json: str,
        created_at: str,
        accessed_at: str,
        expires_at: str,
    ):
        self.session_id = session_id
        self.site_id = site_id
        self.conversation_json = conversation_json
        self.created_at = created_at
        self.accessed_at = accessed_at
        self.expires_at = expires_at

    @property
    def is_expired(self) -> bool:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return self.expires_at < now

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "site_id": self.site_id,
            "conversation": json.loads(self.conversation_json),
            "created_at": self.created_at,
            "accessed_at": self.accessed_at,
            "expires_at": self.expires_at,
        }


class SessionStore(ABC):
    """Abstract base for session storage backends."""

    @abstractmethod
    def create(self, session_id: str, site_id: str, conversation: dict) -> None:
        """Create a new session."""
        pass

    @abstractmethod
    def get(self, session_id: str, site_id: str) -> Session | None:
        """Get a session by ID. Returns None if not found or expired."""
        pass

    @abstractmethod
    def update(self, session_id: str, site_id: str, conversation: dict) -> None:
        """Update a session's conversation and extend expiry. Raises KeyError if not found."""
        pass

    @abstractmethod
    def delete(self, session_id: str, site_id: str) -> None:
        """Delete a session."""
        pass

    @abstractmethod
    def cleanup_expired(self) -> int:
        """Delete all expired sessions. Returns count deleted."""
        pass


class SQLiteSessionStore(SessionStore):
    """SQLite-backed session storage with TTL eviction."""

    TTL_SECONDS = 24 * 3600  # 24 hours

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DEFAULT_DB
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with connect(self.db_path) as conn:
            conn.execute("PRAGMA user_version = 1")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT NOT NULL,
                    site_id TEXT NOT NULL,
                    conversation_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    accessed_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, site_id),
                    FOREIGN KEY (site_id) REFERENCES sites(site_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sites (
                    site_id TEXT PRIMARY KEY,
                    synced_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def create(self, session_id: str, site_id: str, conversation: dict) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=self.TTL_SECONDS)).isoformat(timespec="seconds")
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, site_id, conversation_json, created_at, accessed_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, site_id, json.dumps(conversation), now, now, expires_at),
            )
            conn.commit()

    def get(self, session_id: str, site_id: str) -> Session | None:
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT session_id, site_id, conversation_json, created_at, accessed_at, expires_at
                FROM sessions
                WHERE session_id = ? AND site_id = ?
                """,
                (session_id, site_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            session = Session(*row)
            if session.is_expired:
                conn.execute("DELETE FROM sessions WHERE session_id = ? AND site_id = ?", (session_id, site_id))
                conn.commit()
                return None
            return session

    def update(self, session_id: str, site_id: str, conversation: dict) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=self.TTL_SECONDS)).isoformat(timespec="seconds")
        with connect(self.db_path) as conn:
            result = conn.execute(
                """
                UPDATE sessions
                SET conversation_json = ?, accessed_at = ?, expires_at = ?
                WHERE session_id = ? AND site_id = ?
                """,
                (json.dumps(conversation), now, expires_at, session_id, site_id),
            )
            conn.commit()
            if result.rowcount == 0:
                raise KeyError(f"Session not found: {session_id} on site {site_id}")

    def delete(self, session_id: str, site_id: str) -> None:
        with connect(self.db_path) as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ? AND site_id = ?", (session_id, site_id))
            conn.commit()

    def cleanup_expired(self) -> int:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            conn.commit()
            return cursor.rowcount


class RedisSessionStore(SessionStore):
    """
    Session storage shared across hosts.

    Only needed when the API is served from more than one machine. A single
    host running several workers is already covered by SQLiteSessionStore,
    because WAL mode coordinates concurrent processes.

    Expiry is delegated to Redis key TTLs rather than a stored timestamp, so
    abandoned sessions are reclaimed without a sweeper process. Keys are
    namespaced by site_id, which keeps tenant isolation identical to the
    SQLite store's composite primary key.
    """

    TTL_SECONDS = 24 * 3600

    def __init__(self, client: Any, namespace: str = "aurora:sess:"):
        self.client = client
        self.namespace = namespace

    def _key(self, session_id: str, site_id: str) -> str:
        return f"{self.namespace}{site_id}:{session_id}"

    def create(self, session_id: str, site_id: str, conversation: dict) -> None:
        now = datetime.now(timezone.utc)
        payload = {
            "session_id": session_id,
            "site_id": site_id,
            "conversation_json": json.dumps(conversation),
            "created_at": now.isoformat(timespec="seconds"),
            "accessed_at": now.isoformat(timespec="seconds"),
            "expires_at": (now + timedelta(seconds=self.TTL_SECONDS)).isoformat(timespec="seconds"),
        }
        self.client.set(
            self._key(session_id, site_id),
            json.dumps(payload),
            ex=self.TTL_SECONDS,
        )

    def get(self, session_id: str, site_id: str) -> Session | None:
        raw = self.client.get(self._key(session_id, site_id))
        if raw is None:
            return None

        payload = json.loads(raw)
        session = Session(
            payload["session_id"],
            payload["site_id"],
            payload["conversation_json"],
            payload["created_at"],
            payload["accessed_at"],
            payload["expires_at"],
        )
        # Redis TTL should have removed it already; this guards against a key
        # written with a stale expiry and keeps behaviour identical to SQLite.
        if session.is_expired:
            self.delete(session_id, site_id)
            return None
        return session

    def update(self, session_id: str, site_id: str, conversation: dict) -> None:
        key = self._key(session_id, site_id)
        raw = self.client.get(key)
        if raw is None:
            raise KeyError(f"Session not found: {session_id} on site {site_id}")

        now = datetime.now(timezone.utc)
        payload = json.loads(raw)
        payload["conversation_json"] = json.dumps(conversation)
        payload["accessed_at"] = now.isoformat(timespec="seconds")
        payload["expires_at"] = (now + timedelta(seconds=self.TTL_SECONDS)).isoformat(timespec="seconds")

        self.client.set(key, json.dumps(payload), ex=self.TTL_SECONDS)

    def delete(self, session_id: str, site_id: str) -> None:
        self.client.delete(self._key(session_id, site_id))

    def cleanup_expired(self) -> int:
        """Redis expires keys itself, so there is nothing to sweep."""
        return 0


def build_session_store(backend: str | None = None) -> SessionStore:
    """
    Construct the configured session store.

    AURORA_SESSION_BACKEND selects the implementation:
      sqlite (default) - shared across workers on one host, no extra services
      redis            - shared across hosts, requires a reachable Redis
    """
    choice = (backend or os.getenv("AURORA_SESSION_BACKEND", "sqlite")).strip().casefold()

    if choice == "sqlite":
        return SQLiteSessionStore()
    if choice == "redis":
        import redis_support

        return RedisSessionStore(redis_support.get_client())

    raise ValueError(
        f"Unknown AURORA_SESSION_BACKEND '{choice}'. Expected sqlite or redis."
    )
