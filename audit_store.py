"""Local, append-audited review queue for the POC. No external data is sent."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

DEFAULT_DB = Path(__file__).resolve().parent / "data" / "local" / "review_queue.sqlite3"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _cipher() -> Fernet | None:
    key = os.getenv("AUDIT_ENCRYPTION_KEY")
    return Fernet(key.encode()) if key else None


def _encode(value: dict) -> tuple[str, str]:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    cipher = _cipher()
    if cipher:
        return "fernet:" + cipher.encrypt(raw).decode(), "FERNET"
    return "plain:" + raw.decode(), "PLAINTEXT_LOCAL_POC"


def _decode(value: str) -> dict:
    if value.startswith("fernet:"):
        cipher = _cipher()
        if not cipher:
            raise RuntimeError("AUDIT_ENCRYPTION_KEY is required to read this review")
        try:
            return json.loads(cipher.decrypt(value.removeprefix("fernet:").encode()).decode())
        except InvalidToken as error:
            raise RuntimeError("Audit encryption key is invalid") from error
    return json.loads(value.removeprefix("plain:"))


def _check_reviewer(reviewer: str) -> None:
    configured = {value.strip() for value in os.getenv("AUDIT_APPROVERS", "").split(",") if value.strip()}
    if configured and reviewer not in configured:
        raise PermissionError(f"reviewer {reviewer!r} is not in AUDIT_APPROVERS")


def initialise(db_path: Path = DEFAULT_DB) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                review_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('PENDING', 'APPROVED', 'REJECTED')),
                payload_json TEXT NOT NULL,
                retention_until TEXT,
                encryption_state TEXT,
                reviewer TEXT,
                decision_note TEXT
            );
            CREATE TABLE IF NOT EXISTS review_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                details_json TEXT NOT NULL,
                FOREIGN KEY(review_id) REFERENCES reviews(review_id)
            );
            """
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(reviews)")}
        if "retention_until" not in columns:
            connection.execute("ALTER TABLE reviews ADD COLUMN retention_until TEXT")
        if "encryption_state" not in columns:
            connection.execute("ALTER TABLE reviews ADD COLUMN encryption_state TEXT")
    try:
        db_path.chmod(0o600)
    except OSError:
        pass


def create_review(payload: dict, db_path: Path = DEFAULT_DB, retention_days: int = 30, require_encryption: bool = False) -> str:
    initialise(db_path)
    review_id = f"REV-{uuid.uuid4().hex[:10].upper()}"
    timestamp = _now()
    encoded, encryption_state = _encode(payload)
    if require_encryption and encryption_state != "FERNET":
        raise RuntimeError("AUDIT_ENCRYPTION_KEY is required when encryption is mandatory")
    retention_until = (datetime.now(timezone.utc) + timedelta(days=retention_days)).isoformat(timespec="seconds")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO reviews (review_id, created_at, updated_at, status, payload_json, retention_until, encryption_state, reviewer, decision_note) VALUES (?, ?, ?, 'PENDING', ?, ?, ?, NULL, NULL)",
            (review_id, timestamp, timestamp, encoded, retention_until, encryption_state),
        )
        connection.execute(
            "INSERT INTO review_events (review_id, occurred_at, event_type, actor, details_json) VALUES (?, ?, 'CREATED', 'bot', '{}')",
            (review_id, timestamp),
        )
    return review_id


def decide_review(review_id: str, status: str, reviewer: str, note: str = "", db_path: Path = DEFAULT_DB) -> None:
    if status not in {"APPROVED", "REJECTED"}:
        raise ValueError("status must be APPROVED or REJECTED")
    _check_reviewer(reviewer)
    initialise(db_path)
    timestamp = _now()
    with sqlite3.connect(db_path) as connection:
        updated = connection.execute(
            "UPDATE reviews SET status=?, updated_at=?, reviewer=?, decision_note=? WHERE review_id=? AND status='PENDING'",
            (status, timestamp, reviewer, note, review_id),
        ).rowcount
        if updated != 1:
            raise ValueError("review does not exist or has already been decided")
        connection.execute(
            "INSERT INTO review_events (review_id, occurred_at, event_type, actor, details_json) VALUES (?, ?, ?, ?, ?)",
            (review_id, timestamp, status, reviewer, json.dumps({"note": note}, ensure_ascii=False)),
        )


def get_review(review_id: str, db_path: Path = DEFAULT_DB) -> dict | None:
    initialise(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM reviews WHERE review_id=?", (review_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result["payload"] = _decode(result.pop("payload_json"))
    return result


def purge_expired(db_path: Path = DEFAULT_DB, before: str | None = None) -> int:
    """Delete expired review payloads and events according to the configured retention deadline."""
    initialise(db_path)
    cutoff = before or _now()
    with sqlite3.connect(db_path) as connection:
        ids = [row[0] for row in connection.execute("SELECT review_id FROM reviews WHERE retention_until IS NOT NULL AND retention_until < ?", (cutoff,))]
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        connection.execute(f"DELETE FROM review_events WHERE review_id IN ({placeholders})", ids)
        connection.execute(f"DELETE FROM reviews WHERE review_id IN ({placeholders})", ids)
    return len(ids)
