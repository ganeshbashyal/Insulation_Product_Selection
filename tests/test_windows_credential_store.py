from __future__ import annotations

import secrets
import sys

import pytest

from windows_credential_store import (
    CRED_MAX_BLOB_SIZE,
    CredentialStoreError,
    WindowsCredentialStore,
)


def test_store_is_limited_to_windows_credential_manager():
    if sys.platform == "win32":
        pytest.skip("Windows-specific rejection check")
    with pytest.raises(CredentialStoreError, match="requires Windows Credential Manager"):
        WindowsCredentialStore()


@pytest.mark.skipif(sys.platform != "win32", reason="Uses the current Windows user's Credential Manager")
def test_windows_credential_manager_round_trip_and_secret_redaction():
    store = WindowsCredentialStore()
    marker = "Matrix local credential test " + secrets.token_hex(8)
    password = secrets.token_urlsafe(30)
    entry_id = None
    try:
        saved = store.save(entry_id=None, label=marker, username="local-test-user",
                           password=password, notes="temporary self-test entry")
        entry_id = saved["id"]
        rows = store.list_entries()
        listed = next(row for row in rows if row["id"] == entry_id)
        assert listed["label"] == marker
        assert "password" not in listed
        assert store.read(entry_id)["password"] == password
        assert store.delete(entry_id)
        entry_id = None
        assert store.read(saved["id"]) is None
    finally:
        if entry_id:
            store.delete(entry_id)


def test_windows_blob_size_is_bounded():
    assert CRED_MAX_BLOB_SIZE == 2560
