"""Private local persistence and owner authentication for Oracle."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from pathlib import Path

from local_db import connect as local_connect, state_path


DEFAULT_DB = state_path("oracle.sqlite3")
SESSION_SECONDS = 8 * 3600
PASSWORD_ROUNDS = 600_000


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class OracleStore:
    def __init__(self, path: Path | None = None):
        self.path = path or DEFAULT_DB
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS oracle_owner (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    salt TEXT NOT NULL,
                    passphrase_hash TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oracle_login_attempts (
                    address_hash TEXT NOT NULL,
                    occurred REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oracle_sessions (
                    token_hash TEXT PRIMARY KEY,
                    csrf TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oracle_conversations (
                    conversation_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    model TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oracle_messages (
                    id INTEGER PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES oracle_conversations(conversation_id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL,
                    citations_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oracle_notes (
                    note_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_refs_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oracle_tasks (
                    task_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    details TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('open','in_progress','done')),
                    due_date TEXT,
                    source_refs_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS oracle_messages_conversation
                    ON oracle_messages(conversation_id, id);
                CREATE INDEX IF NOT EXISTS oracle_conversations_updated
                    ON oracle_conversations(updated_at DESC);
                CREATE INDEX IF NOT EXISTS oracle_tasks_updated
                    ON oracle_tasks(status, updated_at DESC);
            """)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    @contextmanager
    def connection(self):
        with local_connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            yield conn

    def configured(self) -> bool:
        with self.connection() as conn:
            return conn.execute("SELECT 1 FROM oracle_owner WHERE singleton=1").fetchone() is not None

    def set_passphrase(self, passphrase: str, *, reset: bool = False) -> None:
        if not isinstance(passphrase, str) or not 14 <= len(passphrase) <= 256:
            raise ValueError("Oracle passphrase must contain 14-256 characters")
        salt = secrets.token_bytes(16)
        password_hash = hashlib.pbkdf2_hmac(
            "sha256", passphrase.encode("utf-8"), salt, PASSWORD_ROUNDS
        ).hex()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            exists = conn.execute("SELECT 1 FROM oracle_owner WHERE singleton=1").fetchone()
            if exists and not reset:
                raise ValueError("Oracle owner passphrase is already configured; use the local reset command")
            conn.execute("""
                INSERT INTO oracle_owner(singleton,salt,passphrase_hash,updated_at)
                VALUES(1,?,?,?)
                ON CONFLICT(singleton) DO UPDATE SET
                    salt=excluded.salt, passphrase_hash=excluded.passphrase_hash, updated_at=excluded.updated_at
            """, (salt.hex(), password_hash, _stamp()))
            conn.execute("DELETE FROM oracle_sessions")
            conn.execute("DELETE FROM oracle_login_attempts")

    def login(self, passphrase: str, address: str) -> dict:
        address_hash = _digest(address or "unknown")
        now = time.time()
        failure = None
        session_data = None
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM oracle_login_attempts WHERE occurred<?", (now - 900,))
            attempts = conn.execute(
                "SELECT COUNT(*) FROM oracle_login_attempts WHERE address_hash=?", (address_hash,)
            ).fetchone()[0]
            if attempts >= 10:
                failure = "Too many Oracle login attempts; wait 15 minutes"
            else:
                conn.execute("INSERT INTO oracle_login_attempts VALUES(?,?)", (address_hash, now))
                row = conn.execute("SELECT salt,passphrase_hash FROM oracle_owner WHERE singleton=1").fetchone()
                if row:
                    supplied = hashlib.pbkdf2_hmac(
                        "sha256", passphrase.encode("utf-8"), bytes.fromhex(row["salt"]), PASSWORD_ROUNDS
                    ).hex()
                else:
                    hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), bytes(16), PASSWORD_ROUNDS)
                    supplied = ""
                if not row or not hmac.compare_digest(supplied, row["passphrase_hash"]):
                    failure = "Invalid Oracle passphrase"
                else:
                    conn.execute("DELETE FROM oracle_login_attempts WHERE address_hash=?", (address_hash,))
                    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
                    conn.execute("INSERT INTO oracle_sessions VALUES(?,?,?,?)",
                                 (_digest(token), csrf, _stamp(), now + SESSION_SECONDS))
                    session_data = {"token": token, "csrf": csrf}
        if failure:
            raise ValueError(failure)
        return session_data

    def session(self, token: str) -> dict | None:
        if not token:
            return None
        with self.connection() as conn:
            row = conn.execute(
                "SELECT csrf,expires FROM oracle_sessions WHERE token_hash=?", (_digest(token),)
            ).fetchone()
            if not row:
                return None
            if row["expires"] <= time.time():
                conn.execute("DELETE FROM oracle_sessions WHERE token_hash=?", (_digest(token),))
                return None
            return {"csrf": row["csrf"]}

    def logout(self, token: str) -> None:
        with self.connection() as conn:
            conn.execute("DELETE FROM oracle_sessions WHERE token_hash=?", (_digest(token),))

    def create_conversation(self, conversation_id: str, scope: str, environment: str,
                            model: str, context: dict) -> dict:
        now = _stamp()
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO oracle_conversations
                (conversation_id,title,scope,environment,model,context_json,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?)
            """, (conversation_id, "New Oracle conversation", scope, environment, model,
                  _canonical(context), now, now))
        return self.conversation(conversation_id)

    def conversations(self, limit: int = 100) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("""
                SELECT c.*,(SELECT COUNT(*) FROM oracle_messages m
                            WHERE m.conversation_id=c.conversation_id) AS message_count
                FROM oracle_conversations c ORDER BY updated_at DESC LIMIT ?
            """, (limit,)).fetchall()
        return [self._conversation_row(row) for row in rows]

    @staticmethod
    def _conversation_row(row) -> dict:
        value = dict(row)
        value["context"] = json.loads(value.pop("context_json"))
        return value

    def conversation(self, conversation_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM oracle_conversations WHERE conversation_id=?", (conversation_id,)
            ).fetchone()
        return self._conversation_row(row) if row else None

    def messages(self, conversation_id: str) -> list[dict]:
        with self.connection() as conn:
            if not conn.execute("SELECT 1 FROM oracle_conversations WHERE conversation_id=?",
                                (conversation_id,)).fetchone():
                raise KeyError("Oracle conversation not found")
            rows = conn.execute("""
                SELECT role,content,citations_json,occurred_at FROM oracle_messages
                WHERE conversation_id=? ORDER BY id
            """, (conversation_id,)).fetchall()
        return [{**dict(row), "citations": json.loads(row["citations_json"])} for row in rows]

    def update_conversation(self, conversation_id: str, *, title: str | None = None,
                            scope: str | None = None, environment: str | None = None,
                            model: str | None = None, context: dict | None = None) -> dict:
        current = self.conversation(conversation_id)
        if not current:
            raise KeyError("Oracle conversation not found")
        values = (
            title if title is not None else current["title"],
            scope if scope is not None else current["scope"],
            environment if environment is not None else current["environment"],
            model if model is not None else current["model"],
            _canonical(context if context is not None else current["context"]),
            _stamp(), conversation_id,
        )
        with self.connection() as conn:
            conn.execute("""
                UPDATE oracle_conversations SET title=?,scope=?,environment=?,model=?,context_json=?,updated_at=?
                WHERE conversation_id=?
            """, values)
        return self.conversation(conversation_id)

    def add_message(self, conversation_id: str, role: str, content: str,
                    citations: list[dict] | None = None) -> dict:
        if role not in {"user", "assistant"}:
            raise ValueError("Invalid Oracle message role")
        now = _stamp()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT title FROM oracle_conversations WHERE conversation_id=?",
                               (conversation_id,)).fetchone()
            if not row:
                raise KeyError("Oracle conversation not found")
            conn.execute("""
                INSERT INTO oracle_messages(conversation_id,role,content,citations_json,occurred_at)
                VALUES(?,?,?,?,?)
            """, (conversation_id, role, content, _canonical(citations or []), now))
            title = row["title"]
            if role == "user" and title == "New Oracle conversation":
                title = content.strip().splitlines()[0][:80] or title
            conn.execute("UPDATE oracle_conversations SET title=?,updated_at=? WHERE conversation_id=?",
                         (title, now, conversation_id))
        return {"role": role, "content": content, "citations": citations or [], "occurred_at": now}

    def delete_conversation(self, conversation_id: str) -> bool:
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM oracle_messages WHERE conversation_id=?", (conversation_id,))
            return conn.execute("DELETE FROM oracle_conversations WHERE conversation_id=?",
                                (conversation_id,)).rowcount == 1

    def notes(self, limit: int = 100) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM oracle_notes ORDER BY updated_at DESC LIMIT ?",
                                (limit,)).fetchall()
        return [{**dict(row), "source_refs": json.loads(row["source_refs_json"])} for row in rows]

    def save_note(self, note_id: str, title: str, content: str, source_refs: list[dict]) -> dict:
        now = _stamp()
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO oracle_notes VALUES(?,?,?,?,?,?)
                ON CONFLICT(note_id) DO UPDATE SET title=excluded.title,content=excluded.content,
                    source_refs_json=excluded.source_refs_json,updated_at=excluded.updated_at
            """, (note_id, title, content, _canonical(source_refs), now, now))
            row = conn.execute("SELECT * FROM oracle_notes WHERE note_id=?", (note_id,)).fetchone()
        return {**dict(row), "source_refs": json.loads(row["source_refs_json"])}

    def delete_note(self, note_id: str) -> bool:
        with self.connection() as conn:
            return conn.execute("DELETE FROM oracle_notes WHERE note_id=?", (note_id,)).rowcount == 1

    def tasks(self, limit: int = 100) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM oracle_tasks ORDER BY updated_at DESC LIMIT ?",
                                (limit,)).fetchall()
        return [{**dict(row), "source_refs": json.loads(row["source_refs_json"])} for row in rows]

    def save_task(self, task_id: str, title: str, details: str, status: str,
                  due_date: str | None, source_refs: list[dict]) -> dict:
        if status not in {"open", "in_progress", "done"}:
            raise ValueError("Invalid Oracle task status")
        now = _stamp()
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO oracle_tasks VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(task_id) DO UPDATE SET title=excluded.title,details=excluded.details,
                    status=excluded.status,due_date=excluded.due_date,source_refs_json=excluded.source_refs_json,
                    updated_at=excluded.updated_at
            """, (task_id, title, details, status, due_date, _canonical(source_refs), now, now))
            row = conn.execute("SELECT * FROM oracle_tasks WHERE task_id=?", (task_id,)).fetchone()
        return {**dict(row), "source_refs": json.loads(row["source_refs_json"])}

    def delete_task(self, task_id: str) -> bool:
        with self.connection() as conn:
            return conn.execute("DELETE FROM oracle_tasks WHERE task_id=?", (task_id,)).rowcount == 1
