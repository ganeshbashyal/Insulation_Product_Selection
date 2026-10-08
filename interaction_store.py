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

import calendar
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from local_db import connect, state_path

DEFAULT_DB = state_path("interactions.sqlite3")

OUTCOMES = ("approved", "edited", "rejected")
CONVERSATION_RETENTION_DAYS = 30
LEAD_RETENTION_MONTHS = 12


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _months_before(value: datetime, months: int) -> datetime:
    month_index = value.year * 12 + value.month - 1 - months
    year, month = divmod(month_index, 12)
    month += 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def purge_expired(now: datetime | None = None, db_path: Path | None = None) -> dict[str, int]:
    """Delete expired interaction records and leads using UTC retention cutoffs."""
    db_path = db_path or DEFAULT_DB
    initialise(db_path)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("Housekeeping time must include a timezone")
    current = current.astimezone(timezone.utc)
    conversation_cutoff = (
        current - timedelta(days=CONVERSATION_RETENTION_DAYS)
    ).isoformat(timespec="seconds")
    lead_cutoff = _months_before(current, LEAD_RETENTION_MONTHS).isoformat(timespec="seconds")

    with closing(connect(db_path)) as connection, connection:
        turns = connection.execute(
            "DELETE FROM conversation_turns WHERE occurred_at < ?",
            (conversation_cutoff,),
        )
        outcomes = connection.execute(
            """
            DELETE FROM outcomes
            WHERE EXISTS (
                SELECT 1 FROM conversations c
                WHERE c.conversation_id = outcomes.conversation_id
                  AND c.site_id = outcomes.site_id
                  AND c.occurred_at < ?
            )
            """,
            (conversation_cutoff,),
        )
        conversations = connection.execute(
            "DELETE FROM conversations WHERE occurred_at < ?",
            (conversation_cutoff,),
        )
        leads = connection.execute(
            "DELETE FROM leads WHERE created_at < ?",
            (lead_cutoff,),
        )
    return {
        "turns": turns.rowcount,
        "conversations": conversations.rowcount,
        "outcomes": outcomes.rowcount,
        "leads": leads.rowcount,
    }


def initialise(db_path: Path | None = None) -> None:
    db_path = db_path or DEFAULT_DB
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(db_path)) as connection, connection:
        connection.execute("PRAGMA user_version = 4")
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
                sales_brief_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (conversation_id, site_id),
                FOREIGN KEY (site_id) REFERENCES sites(site_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_turns (
                turn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                turn_number INTEGER NOT NULL,
                occurred_at TEXT NOT NULL,
                user_message TEXT NOT NULL,
                assistant_reply TEXT NOT NULL,
                category TEXT NOT NULL,
                retrieval_mode TEXT NOT NULL,
                human_review_required INTEGER NOT NULL CHECK (human_review_required IN (0, 1)),
                review_labels_json TEXT NOT NULL,
                UNIQUE(site_id, session_id, turn_number)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS conversation_turns_recent "
            "ON conversation_turns(site_id, turn_id DESC)"
        )
        if "sales_brief_json" not in {row[1] for row in connection.execute("PRAGMA table_info(leads)")}:
            connection.execute("ALTER TABLE leads ADD COLUMN sales_brief_json TEXT NOT NULL DEFAULT '{}'")
        connection.commit()


def log_turn(
    *,
    site_id: str,
    session_id: str,
    conversation_id: str,
    turn_number: int,
    user_message: str,
    assistant_reply: str,
    category: str,
    retrieval_mode: str,
    human_review_required: bool,
    review_labels: list[str] | tuple[str, ...] = (),
    db_path: Path | None = None,
) -> int:
    """Persist one complete Aurora turn for the operator-only interaction review."""
    if not site_id or not session_id or not conversation_id or turn_number < 0:
        raise ValueError("A turn requires its site, session, conversation, and non-negative turn number")
    if not isinstance(user_message, str) or not isinstance(assistant_reply, str):
        raise ValueError("Turn messages must be text")
    if not isinstance(human_review_required, bool):
        raise ValueError("Human-review status must be explicit")
    if any(not isinstance(label, str) or not label or len(label) > 100 for label in review_labels):
        raise ValueError("Review labels must be non-empty bounded strings")
    db_path = db_path or DEFAULT_DB
    initialise(db_path)
    with closing(connect(db_path)) as connection, connection:
        cursor = connection.execute(
            """
            INSERT INTO conversation_turns (
                site_id,session_id,conversation_id,turn_number,occurred_at,user_message,
                assistant_reply,category,retrieval_mode,human_review_required,review_labels_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(site_id,session_id,turn_number) DO UPDATE SET
                conversation_id=excluded.conversation_id,
                occurred_at=excluded.occurred_at,
                user_message=excluded.user_message,
                assistant_reply=excluded.assistant_reply,
                category=excluded.category,
                retrieval_mode=excluded.retrieval_mode,
                human_review_required=excluded.human_review_required,
                review_labels_json=excluded.review_labels_json
            """,
            (
                site_id, session_id, conversation_id, turn_number, _now(),
                user_message, assistant_reply, category, retrieval_mode,
                int(human_review_required), json.dumps(list(review_labels), ensure_ascii=False),
            ),
        )
        row = connection.execute(
            "SELECT turn_id FROM conversation_turns WHERE site_id=? AND session_id=? AND turn_number=?",
            (site_id, session_id, turn_number),
        ).fetchone()
    return int(row[0])


def turn_history(
    site_id: str,
    *,
    before_turn_id: int | None = None,
    limit: int = 500,
    db_path: Path | None = None,
) -> dict:
    """Return one operator-authorized page of complete turns and a stable cursor."""
    if not 1 <= limit <= 500:
        raise ValueError("Turn history page size must be between 1 and 500")
    if before_turn_id is not None and (isinstance(before_turn_id, bool) or before_turn_id <= 0):
        raise ValueError("Turn history cursor must be a positive turn ID")
    db_path = db_path or DEFAULT_DB
    initialise(db_path)
    query = (
        "SELECT turn_id,site_id,session_id,conversation_id,turn_number,occurred_at,"
        "user_message,assistant_reply,category,retrieval_mode,human_review_required,"
        "review_labels_json FROM conversation_turns WHERE site_id=?"
    )
    params: list[object] = [site_id]
    if before_turn_id is not None:
        query += " AND turn_id<?"
        params.append(before_turn_id)
    query += " ORDER BY turn_id DESC LIMIT ?"
    params.append(limit + 1)
    with closing(connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, params).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    turns = []
    for row in rows:
        turn = dict(row)
        turn["human_review_required"] = bool(turn["human_review_required"])
        turn["review_labels"] = json.loads(turn.pop("review_labels_json"))
        turns.append(turn)
    cursor = turns[-1]["turn_id"] if has_more and turns else None
    return {"turns": turns, "next_cursor": cursor}


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
    with closing(connect(db_path)) as connection, connection:
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
    sales_brief: dict | None = None,
) -> None:
    """Persist the personal details and brief captured at the end of a chat."""
    db_path = db_path or DEFAULT_DB
    initialise(db_path)
    now = _now()
    with closing(connect(db_path)) as connection, connection:
        connection.execute(
            "INSERT OR REPLACE INTO leads (conversation_id, site_id, created_at, customer_name, phone, email, callback_time, problem_statement, recommended_families_json, consent_text, consent_at, sales_brief_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                json.dumps(sales_brief or {}, ensure_ascii=False),
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
    with closing(connect(db_path)) as connection, connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, params).fetchall()
    out = []
    for row in rows:
        record = dict(row)
        record["recommended_families"] = json.loads(record.pop("recommended_families_json") or "[]")
        record["sales_brief"] = json.loads(record.pop("sales_brief_json") or "{}")
        out.append(record)
    return out


def sales_briefs(site_id: str, db_path: Path | None = None) -> list[dict]:
    """Operator-only view; older leads remain explicitly unreviewed."""
    results = []
    for lead in leads(db_path=db_path, site_id=site_id):
        brief = lead.pop("sales_brief")
        if not brief:
            brief = {
                "decision_status": "LEGACY_REQUIRES_REVIEW", "approval": None,
                "candidates": [{**family, "disposition": "HOLD", "reasons": ["Legacy recommendation; installation/source review was not captured."]} for family in lead["recommended_families"]],
                "delivery_status": "saved_locally_not_sent",
            }
        results.append({**lead, "sales_brief": brief})
    return results


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
    with closing(connect(db_path)) as connection, connection:
        if connection.execute("SELECT 1 FROM conversations WHERE conversation_id = ? AND site_id = ?", (conversation_id, site_id)).fetchone() is None:
            raise ValueError("Conversation not found for this site")
        connection.execute(
            "INSERT OR REPLACE INTO outcomes (conversation_id, site_id, decided_at, reviewer, outcome, corrected_family_id, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (conversation_id, site_id, _now(), reviewer, outcome, corrected_family_id, note),
        )
        connection.commit()


def family_stats(db_path: Path | None = None) -> list[dict]:
    """Recommendation counts and reviewer outcomes per family."""
    db_path = db_path or DEFAULT_DB
    initialise(db_path)
    with closing(connect(db_path)) as connection, connection:
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
    with closing(connect(db_path)) as connection, connection:
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
    with closing(connect(db_path)) as connection, connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT c.conversation_id, c.site_id, c.occurred_at, c.recommended_family_name, c.gate_status
            FROM conversations c
            LEFT JOIN outcomes o ON o.conversation_id = c.conversation_id AND o.site_id = c.site_id
            WHERE o.conversation_id IS NULL AND (c.recommended_family_id IS NOT NULL OR c.candidates_json != '[]')
            ORDER BY c.occurred_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]
