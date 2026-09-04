from cryptography.fernet import Fernet

from audit_store import create_review, decide_review, get_review, purge_expired


def test_review_is_persisted_and_append_audited(tmp_path):
    database = tmp_path / "reviews.sqlite3"
    review_id = create_review({"customer": "Demo"}, database)
    assert get_review(review_id, database)["status"] == "PENDING"
    decide_review(review_id, "APPROVED", "sales-engineer", "checked", database)
    record = get_review(review_id, database)
    assert record["status"] == "APPROVED"
    assert record["reviewer"] == "sales-engineer"


def test_review_cannot_be_decided_twice(tmp_path):
    database = tmp_path / "reviews.sqlite3"
    review_id = create_review({}, database)
    decide_review(review_id, "REJECTED", "reviewer", db_path=database)
    try:
        decide_review(review_id, "APPROVED", "reviewer", db_path=database)
    except ValueError:
        pass
    else:
        raise AssertionError("a decided review must be immutable")


def test_review_payload_can_be_encrypted(tmp_path, monkeypatch):
    database = tmp_path / "reviews.sqlite3"
    monkeypatch.setenv("AUDIT_ENCRYPTION_KEY", Fernet.generate_key().decode())
    review_id = create_review({"phone": "+61000000000"}, database, require_encryption=True)
    assert get_review(review_id, database)["payload"]["phone"] == "+61000000000"
    assert get_review(review_id, database)["encryption_state"] == "FERNET"


def test_reviewer_allowlist_and_retention(tmp_path, monkeypatch):
    database = tmp_path / "reviews.sqlite3"
    review_id = create_review({}, database, retention_days=0)
    monkeypatch.setenv("AUDIT_APPROVERS", "authorised-person")
    try:
        decide_review(review_id, "APPROVED", "unknown", db_path=database)
    except PermissionError:
        pass
    else:
        raise AssertionError("unknown reviewer should be blocked")
    assert purge_expired(database, "9999-01-01T00:00:00+00:00") == 1
