"""Tests for session storage."""
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from session_store import SQLiteSessionStore, Session


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "sessions.sqlite3"
        yield db_path


@pytest.fixture
def store(temp_db):
    """Create a SessionStore instance."""
    s = SQLiteSessionStore(temp_db)
    yield s
    # Ensure connections are closed before cleanup
    import gc
    gc.collect()


def test_create_and_get(store):
    """Create a session and retrieve it."""
    conversation = {"messages": [{"role": "user", "content": "hi"}]}
    store.create("session_1", "acme", conversation)

    session = store.get("session_1", "acme")
    assert session is not None
    assert session.session_id == "session_1"
    assert session.site_id == "acme"
    assert session.conversation_json == json.dumps(conversation)
    assert not session.is_expired


def test_get_nonexistent_session(store):
    """Get a non-existent session returns None."""
    session = store.get("nonexistent", "acme")
    assert session is None


def test_get_wrong_site(store):
    """Get a session from the wrong site returns None."""
    conversation = {"messages": []}
    store.create("session_1", "acme", conversation)
    session = store.get("session_1", "other_site")
    assert session is None


def test_update_session(store):
    """Update a session's conversation and extend expiry."""
    initial = {"messages": [{"role": "user", "content": "hi"}]}
    store.create("session_1", "acme", initial)

    updated = {"messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]}
    store.update("session_1", "acme", updated)

    session = store.get("session_1", "acme")
    assert session is not None
    assert json.loads(session.conversation_json) == updated


def test_update_nonexistent_raises_error(store):
    """Update non-existent session raises KeyError."""
    with pytest.raises(KeyError):
        store.update("nonexistent", "acme", {})


def test_delete_session(store):
    """Delete a session."""
    conversation = {"messages": []}
    store.create("session_1", "acme", conversation)
    store.delete("session_1", "acme")
    session = store.get("session_1", "acme")
    assert session is None


def test_cleanup_expired(store):
    """Cleanup expired sessions."""
    conversation = {"messages": []}
    store.create("session_1", "acme", conversation)
    store.create("session_2", "acme", conversation)

    # Manually expire session_1 by updating expires_at in DB
    import sqlite3
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE sessions SET expires_at = ? WHERE session_id = ?", (past, "session_1"))
        conn.commit()

    # Cleanup should remove session_1
    deleted_count = store.cleanup_expired()
    assert deleted_count == 1

    # session_1 should be gone, session_2 should remain
    assert store.get("session_1", "acme") is None
    assert store.get("session_2", "acme") is not None


def test_session_to_dict(store):
    """Session.to_dict() returns JSON-safe dict."""
    conversation = {"messages": [{"role": "user", "content": "test"}]}
    store.create("session_1", "acme", conversation)

    session = store.get("session_1", "acme")
    d = session.to_dict()

    assert d["session_id"] == "session_1"
    assert d["site_id"] == "acme"
    assert d["conversation"] == conversation
    # Verify it's JSON-serializable
    json.dumps(d)


def test_multi_site_isolation(store):
    """Sessions are isolated by site_id."""
    conv1 = {"messages": [{"role": "user", "content": "acme question"}]}
    conv2 = {"messages": [{"role": "user", "content": "other question"}]}

    store.create("session_1", "acme", conv1)
    store.create("session_1", "other", conv2)

    # Both should exist independently
    s1 = store.get("session_1", "acme")
    s2 = store.get("session_1", "other")

    assert s1 is not None
    assert s2 is not None
    assert json.loads(s1.conversation_json) == conv1
    assert json.loads(s2.conversation_json) == conv2


def test_ttl_extension_on_update(store):
    """Updating a session extends its TTL."""
    conversation = {"messages": []}
    store.create("session_1", "acme", conversation)

    s1 = store.get("session_1", "acme")
    initial_expiry = s1.expires_at

    # Wait long enough for second to advance (timestamps are in seconds)
    import time
    time.sleep(1.1)
    store.update("session_1", "acme", {"messages": [{"role": "assistant", "content": "updated"}]})

    s2 = store.get("session_1", "acme")
    new_expiry = s2.expires_at

    # New expiry should be later than initial
    assert new_expiry > initial_expiry
