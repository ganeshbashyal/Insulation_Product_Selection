from audit_store import create_review, decide_review, get_review


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
