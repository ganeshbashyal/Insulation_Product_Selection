"""Interaction learning store for the deployable agent.

Logs every completed conversation and its recommendation to SQLite, then lets
a reviewer record an outcome per conversation. Aggregated outcomes show which
families are being recommended and how often reviewers approve / edit / reject
them, so the deterministic ranker and family data can be tuned from real usage.

Deliberately separated from audit_store (which is the human-review queue for
quotes). This store is for *learning from interactions*, not for compliance
records, and never feeds back into live ranking on its own.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent / "data" / "local" / "interactions.sqlite3"

OUTCOMES = ("approved", "edited", "rejected")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def initialise(db_path: Path | None = None) -> None:
    db_path = db_path or DEFAULT_DB
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                occurred_at TEXT NOT NULL,
                answers_json TEXT NOT NULL,
                recommended_family_id TEXT,
                recommended_family_name TEXT,
                gate_status TEXT,
                gate_reason TEXT,
                climate_zone INTEGER,
                candidates_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS outcomes (
                conversation_id TEXT PRIMARY KEY REFERENCES conversations(conversation_id),
                decided_at TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                outcome TEXT NOT NULL CHECK (outcome IN ('approved', 'edited', 'rejected')),
                corrected_family_id TEXT,
                note TEXT NOT NULL DEFAULT ''
            )
            """
        )


def log_conversation(
    conversation_id: str,
    answers: dict,
    recommendation: dict | None,
    gate_status: str,
    gate_reason: str,
    climate_zone: int | None,
    candidates: list[dict],
    db_path: Path | None = None,
) -> None:
    db_path = db_path or DEFAULT_DB
    initialise(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO conversations (conversation_id, occurred_at, answers_json, recommended_family_id, recommended_family_name, gate_status, gate_reason, climate_zone, candidates_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                conversation_id,
                _now(),
                json.dumps(answers, ensure_ascii=False, sort_keys=True),
                (recommendation or {}).get("family_id"),
                (recommendation or {}).get("name"),
                gate_status,
                gate_reason,
                climate_zone,
                json.dumps(candidates, ensure_ascii=False),
            ),
        )


def record_outcome(
    conversation_id: str,
    outcome: str,
    reviewer: str,
    corrected_family_id: str | None = None,
    note: str = "",
    db_path: Path | None = None,
) -> None:
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {OUTCOMES}")
    db_path = db_path or DEFAULT_DB
    initialise(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO outcomes (conversation_id, decided_at, reviewer, outcome, corrected_family_id, note) VALUES (?, ?, ?, ?, ?, ?)",
            (conversation_id, _now(), reviewer, outcome, corrected_family_id, note),
        )


def family_stats(db_path: Path | None = None) -> list[dict]:
    """Recommendation counts and reviewer outcomes per family."""
    db_path = db_path or DEFAULT_DB
    initialise(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT c.recommended_family_id AS family_id,
                   c.recommended_family_name AS family_name,
                   COUNT(*) AS recommended,
                   SUM(CASE WHEN o.outcome = 'approved' THEN 1 ELSE 0 END) AS approved,
                   SUM(CASE WHEN o.outcome = 'edited' THEN 1 ELSE 0 END) AS edited,
                   SUM(CASE WHEN o.outcome = 'rejected' THEN 1 ELSE 0 END) AS rejected
            FROM conversations c
            LEFT JOIN outcomes o ON o.conversation_id = c.conversation_id
            WHERE c.recommended_family_id IS NOT NULL
            GROUP BY c.recommended_family_id
            ORDER BY recommended DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def rejection_report(db_path: Path | None = None, days: int = 90) -> list[dict]:
    """Conversations where the reviewer rejected or corrected the recommendation."""
    initialise(db_path)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT c.conversation_id, c.occurred_at, c.answers_json,
                   c.recommended_family_name, o.outcome, o.corrected_family_id, o.note, o.reviewer
            FROM outcomes o
            JOIN conversations c ON c.conversation_id = o.conversation_id
            WHERE o.outcome IN ('edited', 'rejected') AND o.decided_at >= ?
            ORDER BY o.decided_at DESC
            """,
            (cutoff,),
        ).fetchall()
    return [dict(row) for row in rows]


def pending_review(db_path: Path | None = None) -> list[dict]:
    """Logged conversations that have not yet received a reviewer outcome."""
    db_path = db_path or DEFAULT_DB
    initialise(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT c.conversation_id, c.occurred_at, c.recommended_family_name, c.gate_status
            FROM conversations c
            LEFT JOIN outcomes o ON o.conversation_id = c.conversation_id
            WHERE o.conversation_id IS NULL AND c.recommended_family_id IS NOT NULL
            ORDER BY c.occurred_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


