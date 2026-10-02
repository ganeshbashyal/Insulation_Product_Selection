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

from local_db import connect

DEFAULT_DB = Path(__file__).resolve().parent / "data" / "local" / "interactions.sqlite3"

OUTCOMES = ("approved", "edited", "rejected")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def initialise(db_path: Path | None = None) -> None:
    db_path = db_path or DEFAULT_DB
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as connection:
        connection.execute("PRAGMA user_version = 2")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT NOT NULL,
                site_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                answers_json TEXT NOT NULL,
                recommended_family_id TEXT,
                recommended_family_name TEXT,
                gate_status TEXT,
                gate_reason TEXT,
                climate_zone INTEGER,
                candidates_json TEXT NOT NULL,
                PRIMARY KEY (conversation_id, site_id),
                FOREIGN KEY (site_id) REFERENCES sites(site_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS outcomes (
                conversation_id TEXT NOT NULL,
                site_id TEXT NOT NULL,
                decided_at TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                outcome TEXT NOT NULL CHECK (outcome IN ('approved', 'edited', 'rejected')),
                corrected_family_id TEXT,
                note TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (conversation_id, site_id),
                FOREIGN KEY (conversation_id, site_id) REFERENCES conversations(conversation_id, site_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sites (
                site_id TEXT PRIMARY KEY,
                synced_at TEXT NOT NULL
            )
            """
        )
        # Leads hold customer-supplied personal data, so they live in their own
        # table rather than inside conversations.answers_json. Keeping them
        # separate means a deletion request can drop the personal record
        # without destroying the interaction history the ranker learns from.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                conversation_id TEXT NOT NULL,
                site_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                customer_name TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                callback_time TEXT NOT NULL DEFAULT '',
                problem_statement TEXT NOT NULL DEFAULT '',
                recommended_families_json TEXT NOT NULL DEFAULT '[]',
                consent_text TEXT NOT NULL DEFAULT '',
                consent_at TEXT,
                PRIMARY KEY (conversation_id, site_id),
                FOREIGN KEY (site_id) REFERENCES sites(site_id)
            )
            """
        )
        connection.commit()


def log_conversation(
    conversation_id: str,
    answers: dict,
    recommendation: dict | None,
    gate_status: str,
    gate_reason: str,
    climate_zone: int | None,
    candidates: list[dict],
    site_id: str = "default",
    db_path: Path | None = None,
) -> None:
    db_path = db_path or DEFAULT_DB
    initialise(db_path)
    # A name is useful while speaking to the customer, but it is not needed
    # for ranking or learning and must not be copied into the interaction log.
    non_personal_answers = {
        key: value
        for key, value in answers.items()
        if key.casefold() not in {
            "name", "customer_name", "phone", "mobile", "email",
            "contact_details", "callback_time",
        }
    }
    with connect(db_path) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO conversations (conversation_id, site_id, occurred_at, answers_json, recommended_family_id, recommended_family_name, gate_status, gate_reason, climate_zone, candidates_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                conversation_id,
                site_id,
                _now(),
                json.dumps(non_personal_answers, ensure_ascii=False, sort_keys=True),
                (recommendation or {}).get("family_id"),
                (recommendation or {}).get("name"),
                gate_status,
                gate_reason,
                climate_zone,
                json.dumps(candidates, ensure_ascii=False),
            ),
        )
        connection.commit()


def save_lead(
    conversation_id: str,
    site_id: str = "default",
    customer_name: str = "",
    phone: str = "",
    email: str = "",
    callback_time: str = "",
    problem_statement: str = "",
    recommended_families: list[dict] | None = None,
    consent_text: str = "",
    db_path: Path | None = None,
) -> None:
    """Persist the personal details and brief captured at the end of a chat."""
    db_path = db_path or DEFAULT_DB
    initialise(db_path)
    now = _now()
    with connect(db_path) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO leads (conversation_id, site_id, created_at, customer_name, phone, email, callback_time, problem_statement, recommended_families_json, consent_text, consent_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                conversation_id,
                site_id,
                now,
                customer_name,
                phone,
                email,
                callback_time,
                problem_statement,
                json.dumps(recommended_families or [], ensure_ascii=False),
                consent_text,
                # Consent is only meaningful once the customer actually handed
                # over contact details having been shown the wording.
                now if (phone or email) and consent_text else None,
            ),
        )
        connection.commit()


def leads(db_path: Path | None = None, site_id: str | None = None) -> list[dict]:
    """Captured leads, newest first, optionally scoped to one site."""
    db_path = db_path or DEFAULT_DB
    initialise(db_path)
    query = "SELECT * FROM leads"
    params: tuple = ()
    if site_id is not None:
        query += " WHERE site_id = ?"
        params = (site_id,)
    query += " ORDER BY created_at DESC"
    with connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, params).fetchall()
    out = []
    for row in rows:
        record = dict(row)
        record["recommended_families"] = json.loads(record.pop("recommended_families_json") or "[]")
        out.append(record)
    return out


def record_outcome(
    conversation_id: str,
    outcome: str,
    reviewer: str,
    corrected_family_id: str | None = None,
    note: str = "",
    site_id: str = "default",
    db_path: Path | None = None,
) -> None:
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {OUTCOMES}")
    db_path = db_path or DEFAULT_DB
    initialise(db_path)
    with connect(db_path) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO outcomes (conversation_id, site_id, decided_at, reviewer, outcome, corrected_family_id, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (conversation_id, site_id, _now(), reviewer, outcome, corrected_family_id, note),
        )
        connection.commit()


def family_stats(db_path: Path | None = None) -> list[dict]:
    """Recommendation counts and reviewer outcomes per family."""
    db_path = db_path or DEFAULT_DB
    initialise(db_path)
    with connect(db_path) as connection:
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
            LEFT JOIN outcomes o ON o.conversation_id = c.conversation_id AND o.site_id = c.site_id
            WHERE c.recommended_family_id IS NOT NULL
            GROUP BY c.recommended_family_id
            ORDER BY recommended DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def rejection_report(db_path: Path | None = None, days: int = 90) -> list[dict]:
    """Conversations where the reviewer rejected or corrected the recommendation."""
    db_path = db_path or DEFAULT_DB
    initialise(db_path)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    with connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT c.conversation_id, c.site_id, c.occurred_at, c.answers_json,
                   c.recommended_family_name, o.outcome, o.corrected_family_id, o.note, o.reviewer
            FROM outcomes o
            JOIN conversations c ON c.conversation_id = o.conversation_id AND c.site_id = o.site_id
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
    with connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT c.conversation_id, c.site_id, c.occurred_at, c.recommended_family_name, c.gate_status
            FROM conversations c
            LEFT JOIN outcomes o ON o.conversation_id = c.conversation_id AND o.site_id = c.site_id
            WHERE o.conversation_id IS NULL AND c.recommended_family_id IS NOT NULL
            ORDER BY c.occurred_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]
