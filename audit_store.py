"""Local, append-audited review queue for the POC. No external data is sent."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent / "data" / "local" / "review_queue.sqlite3"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def create_review(payload: dict, db_path: Path = DEFAULT_DB) -> str:
    initialise(db_path)
    review_id = f"REV-{uuid.uuid4().hex[:10].upper()}"
    timestamp = _now()
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO reviews VALUES (?, ?, ?, 'PENDING', ?, NULL, NULL)",
            (review_id, timestamp, timestamp, encoded),
        )
        connection.execute(
            "INSERT INTO review_events (review_id, occurred_at, event_type, actor, details_json) VALUES (?, ?, 'CREATED', 'bot', '{}')",
            (review_id, timestamp),
        )
    return review_id


def decide_review(review_id: str, status: str, reviewer: str, note: str = "", db_path: Path = DEFAULT_DB) -> None:
    if status not in {"APPROVED", "REJECTED"}:
        raise ValueError("status must be APPROVED or REJECTED")
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
    result["payload"] = json.loads(result.pop("payload_json"))
    return result
