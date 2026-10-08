"""Local named-reviewer sessions, versioned notes/reviews and publication."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import time

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "local" / "product_research.sqlite3"
ROLES = {"reader", "reviewer", "publisher", "admin"}
SESSION_SECONDS = 8 * 3600


class Conflict(ValueError):
    pass


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class ResearchStore:
    def __init__(self, path: Path = DEFAULT_DB):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS users(
              username TEXT PRIMARY KEY, salt TEXT NOT NULL, password_hash TEXT NOT NULL,
              roles TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS sessions(
              token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, csrf TEXT NOT NULL,
              expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS login_attempts(
              identity TEXT NOT NULL, occurred REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS events(
              id INTEGER PRIMARY KEY, occurred TEXT NOT NULL, actor TEXT NOT NULL,
              kind TEXT NOT NULL, target TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS revisions(
              id INTEGER PRIMARY KEY, target TEXT NOT NULL, kind TEXT NOT NULL,
              actor TEXT NOT NULL, occurred TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS proposals(
              id INTEGER PRIMARY KEY, actor TEXT NOT NULL, occurred TEXT NOT NULL,
              baseline TEXT NOT NULL, review_version INTEGER NOT NULL,
              payload TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS active_publication(
              singleton INTEGER PRIMARY KEY CHECK(singleton=1), proposal_id INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(
              id INTEGER PRIMARY KEY, actor TEXT NOT NULL, family_id TEXT NOT NULL,
              kind TEXT NOT NULL, state TEXT NOT NULL, occurred TEXT NOT NULL,
              payload TEXT NOT NULL);
            PRAGMA user_version=1;
            """)

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
    def event(conn, actor, kind, target, payload):
        conn.execute("INSERT INTO events(occurred,actor,kind,target,payload) VALUES(?,?,?,?,?)",
                     (stamp(), actor, kind, target, canonical(payload)))

    def create_user(self, username: str, password: str, roles: list[str], *, actor="local-bootstrap"):
        import re
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{3,64}", username):
            raise ValueError("Username must be 3-64 letters, numbers, dots, dashes or underscores")
        if len(password) < 14 or len(password) > 256:
            raise ValueError("Password must contain 14-256 characters")
        if not roles or not set(roles).issubset(ROLES):
            raise ValueError("Invalid account roles")
        salt = secrets.token_hex(16)
        hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600000).hex()
        with self.connection() as conn:
            conn.execute("INSERT INTO users(username,salt,password_hash,roles) VALUES(?,?,?,?)",
                         (username, salt, hashed, canonical(sorted(set(roles) | {"reader"}))))
            self.event(conn, actor, "account_created", username, {"roles": roles})

    def set_disabled(self, username: str, disabled: bool, actor="local-bootstrap"):
        with self.connection() as conn:
            if conn.execute("UPDATE users SET disabled=? WHERE username=?", (int(disabled), username)).rowcount != 1:
                raise ValueError("Unknown user")
            conn.execute("DELETE FROM sessions WHERE username=?", (username,))
            self.event(conn, actor, "account_disabled" if disabled else "account_enabled", username, {})

    def login(self, username: str, password: str, address: str) -> dict:
        now = time.time()
        with self.connection() as conn:
            conn.execute("DELETE FROM login_attempts WHERE occurred<?", (now - 900,))
            conn.execute("DELETE FROM sessions WHERE expires<?", (now,))
            for identity in ("user:" + username, "address:" + address):
                if conn.execute("SELECT COUNT(*) FROM login_attempts WHERE identity=?", (identity,)).fetchone()[0] >= 10:
                    raise ValueError("Too many login attempts; wait 15 minutes")
            for identity in ("user:" + username, "address:" + address):
                conn.execute("INSERT INTO login_attempts VALUES(?,?)", (identity, now))
            row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        salt = row["salt"] if row else "00" * 16
        supplied = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600000).hex()
        if not row or row["disabled"] or not hmac.compare_digest(supplied, row["password_hash"]):
            with self.connection() as conn:
                self.event(conn, username, "login_denied", username, {})
            raise ValueError("Invalid credentials or disabled account")
        token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute("SELECT disabled,roles FROM users WHERE username=?", (username,)).fetchone()
            if not current or current["disabled"]:
                raise ValueError("Invalid credentials or disabled account")
            conn.execute("DELETE FROM login_attempts WHERE identity=?", ("user:" + username,))
            conn.execute("INSERT INTO sessions VALUES(?,?,?,?)", (digest(token), username, csrf, now + SESSION_SECONDS))
            self.event(conn, username, "login", username, {})
        return {"token": token, "csrf": csrf, "username": username, "roles": json.loads(row["roles"])}

    def session(self, token: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("""
              SELECT u.username,u.roles,s.csrf FROM sessions s JOIN users u ON u.username=s.username
              WHERE s.token_hash=? AND s.expires>? AND u.disabled=0
            """, (digest(token), time.time())).fetchone()
        return {"username": row["username"], "roles": json.loads(row["roles"]), "csrf": row["csrf"]} if row else None

    def logout(self, token: str):
        with self.connection() as conn:
            row = conn.execute("SELECT username FROM sessions WHERE token_hash=?", (digest(token),)).fetchone()
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token),))
            if row:
                self.event(conn, row["username"], "logout", row["username"], {})

    def history(self, target: str | None = None) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM revisions WHERE target=? ORDER BY id", (target,)).fetchall() if target else conn.execute("SELECT * FROM revisions ORDER BY id").fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def save_revision(self, target, kind, payload, actor, expected: int):
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            user = conn.execute("SELECT roles,disabled FROM users WHERE username=?", (actor,)).fetchone()
            if not user or user["disabled"] or "reviewer" not in json.loads(user["roles"]):
                raise ValueError("An enabled reviewer account is required")
            version = conn.execute("SELECT COALESCE(MAX(id),0) FROM revisions WHERE target=? AND kind=?", (target, kind)).fetchone()[0]
            if version != expected:
                raise Conflict("Record changed; refresh before saving")
            cursor = conn.execute("INSERT INTO revisions(target,kind,actor,occurred,payload) VALUES(?,?,?,?,?)",
                                  (target, kind, actor, stamp(), canonical(payload)))
            self.event(conn, actor, kind, target, {"revision": cursor.lastrowid, **payload})
            return cursor.lastrowid

    def version(self):
        with self.connection() as conn:
            return conn.execute("SELECT COALESCE(MAX(id),0) FROM revisions").fetchone()[0]

    def active(self):
        with self.connection() as conn:
            row = conn.execute("""SELECT p.* FROM proposals p JOIN active_publication a
                                  ON a.proposal_id=p.id WHERE a.singleton=1""").fetchone()
        return {**dict(row), "payload": json.loads(row["payload"])} if row else None

    def preview(self, payload, baseline: str, actor: str):
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            version = conn.execute("SELECT COALESCE(MAX(id),0) FROM revisions").fetchone()[0]
            if payload["review_version"] != version:
                raise Conflict("Reviews changed while building preview")
            cursor = conn.execute("INSERT INTO proposals(actor,occurred,baseline,review_version,payload) VALUES(?,?,?,?,?)",
                                  (actor, stamp(), baseline, version, canonical(payload)))
            self.event(conn, actor, "publish_preview", str(cursor.lastrowid), {"baseline": baseline})
            return cursor.lastrowid

    def publish(self, proposal_id: int, baseline: str, actor: str):
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            user = conn.execute("SELECT roles,disabled FROM users WHERE username=?", (actor,)).fetchone()
            if not user or user["disabled"] or "publisher" not in json.loads(user["roles"]):
                raise ValueError("An enabled publisher account is required")
            row = conn.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
            if not row or row["published"]:
                raise Conflict("Preview missing or already published")
            version = conn.execute("SELECT COALESCE(MAX(id),0) FROM revisions").fetchone()[0]
            if row["baseline"] != baseline or row["review_version"] != version:
                raise Conflict("Sources or reviews changed; create a new preview")
            payload = json.loads(row["payload"])
            if payload.get("blockers"):
                raise ValueError("Resolve publication blockers before publishing")
            reviewers = {item["reviewer"] for item in payload.get("claims", [])}
            reviewers.update(item["reviewer"] for item in payload.get("eligibility", {}).values())
            for reviewer in reviewers:
                account = conn.execute("SELECT roles,disabled FROM users WHERE username=?", (reviewer,)).fetchone()
                if not account or account["disabled"] or "reviewer" not in json.loads(account["roles"]):
                    raise Conflict("Reviewer permissions changed; create a new preview")
            conn.execute("INSERT INTO active_publication VALUES(1,?) ON CONFLICT(singleton) DO UPDATE SET proposal_id=excluded.proposal_id", (proposal_id,))
            conn.execute("UPDATE proposals SET published=1 WHERE id=?", (proposal_id,))
            self.event(conn, actor, "published", str(proposal_id), payload)
            return payload
