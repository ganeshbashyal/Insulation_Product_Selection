"""Isolated local persistence for Family Knowledge Manager conversations and drafts."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "local" / "family_manager.sqlite3"


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class FamilyAssistantStore:
    def __init__(self, path: Path | None = None):
        self.path = path or DEFAULT_DB
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    actor TEXT NOT NULL,
                    family_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL,
                    citations_json TEXT NOT NULL,
                    proposal_id TEXT,
                    occurred_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS proposals (
                    proposal_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
                    actor TEXT NOT NULL,
                    family_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    source_signature TEXT NOT NULL,
                    base_revision INTEGER NOT NULL,
                    baseline_json TEXT NOT NULL,
                    changes_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('draft','saved_to_local_copy')),
                    created_at TEXT NOT NULL,
                    applied_revision INTEGER
                );
                CREATE TABLE IF NOT EXISTS authoring_revisions (
                    revision_id INTEGER PRIMARY KEY,
                    family_id TEXT NOT NULL,
                    revision_number INTEGER NOT NULL,
                    actor TEXT NOT NULL,
                    proposal_id TEXT NOT NULL UNIQUE,
                    source_signature TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(family_id, revision_number)
                );
                CREATE INDEX IF NOT EXISTS conversations_owner_recent
                    ON conversations(actor, updated_at DESC);
                CREATE INDEX IF NOT EXISTS messages_by_conversation
                    ON messages(conversation_id, id);
                CREATE INDEX IF NOT EXISTS proposals_by_conversation
                    ON proposals(conversation_id, created_at);
                CREATE INDEX IF NOT EXISTS family_authoring_revisions
                    ON authoring_revisions(family_id, revision_number DESC);
            """)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _conversation(row) -> dict:
        return dict(row)

    @staticmethod
    def _proposal(row) -> dict:
        value = dict(row)
        value["baseline"] = json.loads(value.pop("baseline_json"))
        value["changes"] = json.loads(value.pop("changes_json"))
        return value

    def create_conversation(self, conversation_id: str, actor: str, family_id: str,
                            model: str) -> dict:
        now = _stamp()
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO conversations
                    (conversation_id,actor,family_id,model,title,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?)
            """, (conversation_id, actor, family_id, model, "New family conversation", now, now))
        return self.conversation(conversation_id, actor)

    def conversations(self, actor: str, family_id: str | None = None,
                      limit: int = 100) -> list[dict]:
        with self.connection() as conn:
            if family_id:
                rows = conn.execute("""
                    SELECT c.*,(SELECT COUNT(*) FROM messages m
                                WHERE m.conversation_id=c.conversation_id) AS message_count
                    FROM conversations c WHERE actor=? AND family_id=?
                    ORDER BY updated_at DESC LIMIT ?
                """, (actor, family_id, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT c.*,(SELECT COUNT(*) FROM messages m
                                WHERE m.conversation_id=c.conversation_id) AS message_count
                    FROM conversations c WHERE actor=? ORDER BY updated_at DESC LIMIT ?
                """, (actor, limit)).fetchall()
        return [dict(row) for row in rows]

    def conversation(self, conversation_id: str, actor: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE conversation_id=? AND actor=?",
                (conversation_id, actor),
            ).fetchone()
        return self._conversation(row) if row else None

    def messages(self, conversation_id: str, actor: str) -> list[dict]:
        with self.connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM conversations WHERE conversation_id=? AND actor=?",
                (conversation_id, actor),
            ).fetchone():
                raise KeyError("Family conversation not found")
            rows = conn.execute("""
                SELECT role,content,citations_json,proposal_id,occurred_at
                FROM messages WHERE conversation_id=? ORDER BY id
            """, (conversation_id,)).fetchall()
        return [{
            "role": row["role"], "content": row["content"],
            "citations": json.loads(row["citations_json"]),
            "proposal_id": row["proposal_id"], "occurred_at": row["occurred_at"],
        } for row in rows]

    def add_message(self, conversation_id: str, actor: str, role: str, content: str,
                    citations: list[dict] | None = None, proposal_id: str | None = None) -> dict:
        if role not in {"user", "assistant"}:
            raise ValueError("Invalid family assistant message role")
        now = _stamp()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT title FROM conversations WHERE conversation_id=? AND actor=?",
                (conversation_id, actor),
            ).fetchone()
            if not row:
                raise KeyError("Family conversation not found")
            conn.execute("""
                INSERT INTO messages
                    (conversation_id,role,content,citations_json,proposal_id,occurred_at)
                VALUES(?,?,?,?,?,?)
            """, (conversation_id, role, content, _canonical(citations or []), proposal_id, now))
            title = row["title"]
            if role == "user" and title == "New family conversation":
                title = content.strip().splitlines()[0][:80] or title
            conn.execute(
                "UPDATE conversations SET title=?,updated_at=? WHERE conversation_id=?",
                (title, now, conversation_id),
            )
        return {
            "role": role, "content": content, "citations": citations or [],
            "proposal_id": proposal_id, "occurred_at": now,
        }

    def delete_conversation(self, conversation_id: str, actor: str) -> bool:
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return conn.execute(
                "DELETE FROM conversations WHERE conversation_id=? AND actor=?",
                (conversation_id, actor),
            ).rowcount == 1

    def create_proposal(self, *, proposal_id: str, conversation_id: str, actor: str,
                        family_id: str, title: str, summary: str, source_signature: str,
                        base_revision: int, baseline: dict, changes: list[dict]) -> dict:
        now = _stamp()
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO proposals
                    (proposal_id,conversation_id,actor,family_id,title,summary,source_signature,
                     base_revision,baseline_json,changes_json,status,created_at)
                SELECT ?,?,?,?,?,?,?,?,?,?,'draft',?
                WHERE EXISTS(SELECT 1 FROM conversations
                             WHERE conversation_id=? AND actor=? AND family_id=?)
            """, (proposal_id, conversation_id, actor, family_id, title, summary,
                  source_signature, base_revision, _canonical(baseline), _canonical(changes), now,
                  conversation_id, actor, family_id))
            if conn.execute("SELECT changes()").fetchone()[0] != 1:
                raise KeyError("Family conversation not found")
        return self.proposal(proposal_id, actor)

    def proposal(self, proposal_id: str, actor: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM proposals WHERE proposal_id=? AND actor=?",
                (proposal_id, actor),
            ).fetchone()
        return self._proposal(row) if row else None

    def proposals(self, conversation_id: str, actor: str) -> list[dict]:
        with self.connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM conversations WHERE conversation_id=? AND actor=?",
                (conversation_id, actor),
            ).fetchone():
                raise KeyError("Family conversation not found")
            rows = conn.execute("""
                SELECT * FROM proposals WHERE conversation_id=? AND actor=?
                ORDER BY created_at DESC
            """, (conversation_id, actor)).fetchall()
        return [self._proposal(row) for row in rows]

    def delete_proposal(self, proposal_id: str, actor: str) -> bool:
        with self.connection() as conn:
            return conn.execute(
                "DELETE FROM proposals WHERE proposal_id=? AND actor=? AND status='draft'",
                (proposal_id, actor),
            ).rowcount == 1

    def authoring_copy(self, family_id: str) -> dict:
        with self.connection() as conn:
            row = conn.execute("""
                SELECT * FROM authoring_revisions WHERE family_id=?
                ORDER BY revision_number DESC LIMIT 1
            """, (family_id,)).fetchone()
        if not row:
            return {"revision": 0, "snapshot": None, "source_signature": None}
        return {
            "revision": row["revision_number"],
            "snapshot": json.loads(row["snapshot_json"]),
            "source_signature": row["source_signature"],
            "actor": row["actor"],
            "created_at": row["created_at"],
        }

    def apply_proposal(self, proposal_id: str, actor: str, *,
                       source_signature: str, expected_revision: int,
                       snapshot: dict) -> dict:
        now = _stamp()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            proposal_row = conn.execute(
                "SELECT * FROM proposals WHERE proposal_id=? AND actor=?",
                (proposal_id, actor),
            ).fetchone()
            if not proposal_row:
                raise KeyError("Family proposal not found")
            proposal = self._proposal(proposal_row)
            if proposal["status"] != "draft":
                raise ValueError("Family proposal is no longer a draft")
            latest = conn.execute(
                "SELECT COALESCE(MAX(revision_number),0) FROM authoring_revisions WHERE family_id=?",
                (proposal["family_id"],),
            ).fetchone()[0]
            if proposal["source_signature"] != source_signature:
                raise ValueError("Family sources changed; refresh and create a new proposal")
            if (proposal["base_revision"] != latest
                    or expected_revision != latest):
                raise ValueError("The private authoring copy changed; refresh before approving")
            revision = latest + 1
            cursor = conn.execute("""
                INSERT INTO authoring_revisions
                    (family_id,revision_number,actor,proposal_id,source_signature,snapshot_json,created_at)
                VALUES(?,?,?,?,?,?,?)
            """, (proposal["family_id"], revision, actor, proposal_id,
                  source_signature, _canonical(snapshot), now))
            conn.execute("""
                UPDATE proposals SET status='saved_to_local_copy',applied_revision=?
                WHERE proposal_id=? AND actor=? AND status='draft'
            """, (revision, proposal_id, actor))
            conn.execute("""
                INSERT INTO messages
                    (conversation_id,role,content,citations_json,proposal_id,occurred_at)
                VALUES(?,'assistant',?,'[]',?,?)
            """, (proposal["conversation_id"],
                  f"Saved your approved changes to the private local authoring copy (revision {revision}). "
                  "Canonical knowledge and deployment files were not changed.",
                  proposal_id, now))
            conn.execute(
                "UPDATE conversations SET updated_at=? WHERE conversation_id=?",
                (now, proposal["conversation_id"]),
            )
            revision_id = cursor.lastrowid
        return {
            "revision_id": revision_id, "revision": revision, "family_id": proposal["family_id"],
            "snapshot": snapshot, "created_at": now, "path": str(self.path),
        }
