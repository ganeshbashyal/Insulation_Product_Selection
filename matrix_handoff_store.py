"""Local Matrix-owned registry for approved, structured Aurora handoffs."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3

from pydantic import BaseModel, ConfigDict, Field, field_validator

from local_db import connect as local_connect, state_path


DEFAULT_DB = state_path("matrix_handoffs.sqlite3")
_CONTACT = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+|\+?\d[\d\s().-]{7,}\d")
DETAIL_FIELDS = {
    "application", "priority", "placement", "project", "project_stage",
    "building_use", "construction", "wall_assembly", "access", "cavity_depth",
    "area", "existing_insulation", "moisture", "airspace", "service",
    "service_temperature", "requirements", "locality", "timeframe", "conditions",
}
_PHONE = re.compile(r"(?:\+?61[\s().-]?|0)[2-478](?:[\s().-]?\d){8}")


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def redact_contact_details(value: str) -> str:
    """Remove contact-like text before project facts cross the Matrix boundary."""
    return re.sub(r"\s+", " ", _PHONE.sub("[contact details omitted]", _CONTACT_EMAIL.sub(
        "[contact details omitted]", value,
    ))).strip()


_CONTACT_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


class HandoffCustomerContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enquiry_type: str = Field(pattern=r"^insulation_project$")


class HandoffConsent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_details_sharing_recorded: bool
    recorded_at: str = Field(min_length=1, max_length=40)
    contact_details_included: bool = False

    @field_validator("contact_details_included")
    @classmethod
    def contact_must_not_be_included(cls, value: bool) -> bool:
        if value:
            raise ValueError("Contact details are not permitted in Matrix handoffs")
        return value

    @field_validator("recorded_at")
    @classmethod
    def validate_recorded_at(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Consent timestamp must be ISO-8601") from exc
        if parsed.tzinfo is None:
            raise ValueError("Consent timestamp must include a timezone")
        return value


class ProvisionalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    review_status: str = Field(pattern=r"^requires_review$")

    @field_validator("family_id", "name")
    @classmethod
    def candidate_text_must_not_contain_contact(cls, value: str) -> str:
        if _CONTACT.search(value):
            raise ValueError("Candidate labels must not contain contact details")
        return value.strip()


class HandoffPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(pattern=r"^aurora$")
    record_type: str = Field(pattern=r"^sales_review$")
    handoff_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    customer_context: HandoffCustomerContext
    problem_description: str = Field(default="", max_length=1200)
    application_details: dict[str, str] = Field(max_length=24)
    unknown_fields: list[str] = Field(max_length=32)
    escalation_flags: list[str] = Field(max_length=8)
    provisional_family_candidates: list[ProvisionalCandidate] = Field(max_length=12)
    consent: HandoffConsent

    @field_validator("problem_description")
    @classmethod
    def problem_must_not_contain_contact(cls, value: str) -> str:
        if _CONTACT.search(value):
            raise ValueError("Problem description must be free of contact details")
        return value.strip()

    @field_validator("application_details")
    @classmethod
    def validate_application_details(cls, value: dict[str, str]) -> dict[str, str]:
        if any(key not in DETAIL_FIELDS for key in value):
            raise ValueError("Handoff contains an unsupported application detail")
        if any(not isinstance(item, str) or not item.strip() or len(item) > 500 or _CONTACT.search(item)
               for item in value.values()):
            raise ValueError("Handoff details must be bounded and free of contact information")
        return {key: item.strip() for key, item in value.items()}

    @field_validator("unknown_fields", "escalation_flags")
    @classmethod
    def validate_labels(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 120 or _CONTACT.search(item) for item in value):
            raise ValueError("Handoff labels must be bounded and free of contact information")
        return [item.strip() for item in value]


class MatrixHandoffStore:
    def __init__(self, path: Path | None = None):
        self.path = path or DEFAULT_DB
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS matrix_handoffs (
                    handoff_id TEXT PRIMARY KEY,
                    source_site_id TEXT NOT NULL,
                    source_conversation_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    consent_recorded_at TEXT NOT NULL,
                    approval_status TEXT NOT NULL CHECK(approval_status='approved'),
                    created_at TEXT NOT NULL,
                    approved_at TEXT NOT NULL,
                    UNIQUE(source_site_id, source_conversation_id)
                );
                CREATE TABLE IF NOT EXISTS matrix_handoff_events (
                    event_id INTEGER PRIMARY KEY,
                    handoff_id TEXT NOT NULL,
                    event_type TEXT NOT NULL CHECK(event_type IN ('approved_handoff_published')),
                    actor TEXT NOT NULL CHECK(actor='operator'),
                    occurred_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS matrix_handoff_created
                    ON matrix_handoffs(created_at DESC);
                CREATE INDEX IF NOT EXISTS matrix_handoff_source
                    ON matrix_handoffs(source_site_id, source_conversation_id);
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

    def publish_approved(
        self,
        payload: HandoffPayload,
        *,
        source_site_id: str,
        source_conversation_id: str,
        consent_recorded_at: str,
        operator_approved: bool,
    ) -> tuple[dict, bool]:
        if not operator_approved:
            raise PermissionError("Explicit operator approval is required")
        if not payload.consent.project_details_sharing_recorded:
            raise PermissionError("Recorded customer consent for project-detail sharing is required")
        if payload.consent.recorded_at != consent_recorded_at:
            raise ValueError("Consent provenance must match the handoff payload")
        if not source_site_id or len(source_site_id) > 100:
            raise ValueError("A valid source site is required")
        if not source_conversation_id or len(source_conversation_id) > 100:
            raise ValueError("A valid source conversation is required")
        if not consent_recorded_at:
            raise PermissionError("Recorded customer consent is required")
        encoded = json.dumps(payload.model_dump(), sort_keys=True, ensure_ascii=False)
        now = _stamp()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT handoff_id,payload_json,created_at,approved_at FROM matrix_handoffs "
                "WHERE source_site_id=? AND source_conversation_id=?",
                (source_site_id, source_conversation_id),
            ).fetchone()
            if existing:
                if existing["handoff_id"] != payload.handoff_id or existing["payload_json"] != encoded:
                    raise ValueError("This Aurora enquiry already has a different immutable handoff")
                return {
                    "handoff_id": existing["handoff_id"],
                    "approval_status": "approved",
                    "created_at": existing["created_at"],
                    "approved_at": existing["approved_at"],
                }, True
            conn.execute(
                "INSERT INTO matrix_handoffs VALUES(?,?,?,?,?,'approved',?,?)",
                (payload.handoff_id, source_site_id, source_conversation_id, encoded,
                 consent_recorded_at, now, now),
            )
            conn.execute(
                "INSERT INTO matrix_handoff_events(handoff_id,event_type,actor,occurred_at) "
                "VALUES(?,?,?,?)",
                (payload.handoff_id, "approved_handoff_published", "operator", now),
            )
        return {
            "handoff_id": payload.handoff_id,
            "approval_status": "approved",
            "created_at": now,
            "approved_at": now,
        }, False

    def approved_handoff(self, handoff_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT payload_json,created_at FROM matrix_handoffs "
                "WHERE handoff_id=? AND approval_status='approved'",
                (handoff_id,),
            ).fetchone()
        if row is None:
            return None
        return {"payload": json.loads(row["payload_json"]), "created_at": row["created_at"]}

    def approved_for_neo(self, limit: int = 100) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError("Handoff list limit must be between 1 and 100")
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT payload_json,created_at FROM matrix_handoffs "
                "WHERE approval_status='approved' ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [{"payload": json.loads(row["payload_json"]), "created_at": row["created_at"]}
                for row in rows]

    def metadata(self, limit: int = 100) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError("Handoff metadata limit must be between 1 and 100")
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT handoff_id,approval_status,created_at,approved_at,consent_recorded_at "
                "FROM matrix_handoffs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [{**dict(row), "handoff_id": row["handoff_id"][:12]}
                for row in rows]

    def metadata_for_source(self, source_site_id: str, source_conversation_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT handoff_id,approval_status,created_at,approved_at "
                "FROM matrix_handoffs WHERE source_site_id=? AND source_conversation_id=?",
                (source_site_id, source_conversation_id),
            ).fetchone()
        if row is None:
            return None
        return {**dict(row), "handoff_id": row["handoff_id"][:12]}


_store: MatrixHandoffStore | None = None


def store() -> MatrixHandoffStore:
    global _store
    if _store is None or _store.path != DEFAULT_DB:
        _store = MatrixHandoffStore(DEFAULT_DB)
    return _store
