"""Private local persistence for the internal Neo sales assistant."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time
import uuid

from local_db import connect as local_connect, state_path


DEFAULT_DB = state_path("neo.sqlite3")


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class NeoStore:
    def __init__(self, path: Path | None = None):
        self.path = path or DEFAULT_DB
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS neo_sessions (
                    token_hash TEXT PRIMARY KEY,
                    csrf TEXT NOT NULL,
                    expires REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS neo_conversations (
                    conversation_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS neo_messages (
                    id INTEGER PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES neo_conversations(conversation_id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL,
                    citations_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS neo_records (
                    record_id TEXT PRIMARY KEY,
                    record_type TEXT NOT NULL CHECK(record_type IN ('review_task','sales_brief')),
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_refs_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS neo_messages_conversation
                    ON neo_messages(conversation_id, id);
                CREATE INDEX IF NOT EXISTS neo_records_created
                    ON neo_records(created_at DESC);
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

    def create_session(self, token_hash: str, csrf: str, expires: float) -> None:
        with self.connection() as conn:
            conn.execute("DELETE FROM neo_sessions")
            conn.execute("INSERT INTO neo_sessions VALUES(?,?,?)", (token_hash, csrf, expires))

    def session(self, token_hash: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT csrf,expires FROM neo_sessions WHERE token_hash=?",
                               (token_hash,)).fetchone()
            if not row:
                return None
            if row["expires"] <= time.time():
                conn.execute("DELETE FROM neo_sessions WHERE token_hash=?", (token_hash,))
                return None
            return {"csrf": row["csrf"]}

    def delete_session(self, token_hash: str) -> None:
        with self.connection() as conn:
            conn.execute("DELETE FROM neo_sessions WHERE token_hash=?", (token_hash,))

    def create_conversation(self, model: str) -> dict:
        identifier, now = str(uuid.uuid4()), _stamp()
        with self.connection() as conn:
            conn.execute("INSERT INTO neo_conversations VALUES(?,?,?,?,?)",
                         (identifier, "New Neo conversation", model, now, now))
        return self.conversation(identifier)

    def conversations(self, limit: int = 60) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("""
                SELECT c.*,(SELECT COUNT(*) FROM neo_messages m
                            WHERE m.conversation_id=c.conversation_id) AS message_count
                FROM neo_conversations c ORDER BY updated_at DESC LIMIT ?
            """, (limit,)).fetchall()
        return [dict(row) for row in rows]

    def conversation(self, conversation_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM neo_conversations WHERE conversation_id=?",
                               (conversation_id,)).fetchone()
        return dict(row) if row else None

    def messages(self, conversation_id: str) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("""
                SELECT role,content,citations_json,occurred_at FROM neo_messages
                WHERE conversation_id=? ORDER BY id
            """, (conversation_id,)).fetchall()
        return [{**dict(row), "citations": json.loads(row["citations_json"])} for row in rows]

    def add_message(self, conversation_id: str, role: str, content: str,
                    citations: list[dict] | None = None) -> dict:
        now = _stamp()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT title FROM neo_conversations WHERE conversation_id=?",
                               (conversation_id,)).fetchone()
            if not row:
                raise KeyError("Neo conversation not found")
            conn.execute("""
                INSERT INTO neo_messages(conversation_id,role,content,citations_json,occurred_at)
                VALUES(?,?,?,?,?)
            """, (conversation_id, role, content,
                  json.dumps(citations or [], ensure_ascii=False), now))
            title = row["title"]
            if role == "user" and title == "New Neo conversation":
                title = content.strip().splitlines()[0][:80] or title
            conn.execute("UPDATE neo_conversations SET title=?,updated_at=? WHERE conversation_id=?",
                         (title, now, conversation_id))
        return {"role": role, "content": content, "citations": citations or [], "occurred_at": now}

    def set_model(self, conversation_id: str, model: str) -> dict | None:
        with self.connection() as conn:
            conn.execute("UPDATE neo_conversations SET model=?,updated_at=? WHERE conversation_id=?",
                         (model, _stamp(), conversation_id))
        return self.conversation(conversation_id)

    def delete_conversation(self, conversation_id: str) -> bool:
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM neo_messages WHERE conversation_id=?", (conversation_id,))
            return conn.execute("DELETE FROM neo_conversations WHERE conversation_id=?",
                                (conversation_id,)).rowcount == 1

    def save_record(self, record_type: str, title: str, content: str,
                    source_refs: list[dict]) -> dict:
        record = {
            "record_id": str(uuid.uuid4()), "record_type": record_type, "title": title,
            "content": content, "source_refs": source_refs, "created_at": _stamp(),
        }
        with self.connection() as conn:
            conn.execute("INSERT INTO neo_records VALUES(?,?,?,?,?,?)", (
                record["record_id"], record_type, title, content,
                json.dumps(source_refs, ensure_ascii=False), record["created_at"],
            ))
        return record

    def records(self, limit: int = 100) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM neo_records ORDER BY created_at DESC LIMIT ?",
                                (limit,)).fetchall()
        return [{**dict(row), "source_refs": json.loads(row["source_refs_json"])} for row in rows]
