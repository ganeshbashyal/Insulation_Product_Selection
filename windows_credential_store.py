"""Small adapter for Windows Credential Manager generic credentials."""
from __future__ import annotations

import ctypes
import json
import secrets
import sys
from ctypes import wintypes


TARGET_PREFIX = "InsulationEasy.Matrix.PasswordManager."
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
CRED_MAX_BLOB_SIZE = 2560
ERROR_NOT_FOUND = 1168


class CredentialStoreError(RuntimeError):
    """Raised when the Windows credential store cannot complete an operation."""


if sys.platform == "win32":
    class _FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    class _CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", _FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._blob_buffer = None


class WindowsCredentialStore:
    """Store opaque application entries in the current Windows user's credential store."""

    def __init__(self):
        if sys.platform != "win32":
            raise CredentialStoreError("The local password manager requires Windows Credential Manager")
        self._api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        self._api.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
        self._api.CredWriteW.restype = wintypes.BOOL
        self._api.CredReadW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)),
        ]
        self._api.CredReadW.restype = wintypes.BOOL
        self._api.CredEnumerateW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(ctypes.POINTER(ctypes.POINTER(_CREDENTIALW))),
        ]
        self._api.CredEnumerateW.restype = wintypes.BOOL
        self._api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self._api.CredDeleteW.restype = wintypes.BOOL
        self._api.CredFree.argtypes = [ctypes.c_void_p]
        self._api.CredFree.restype = None

    @staticmethod
    def _target(entry_id: str) -> str:
        if not isinstance(entry_id, str) or not entry_id.startswith(TARGET_PREFIX):
            raise ValueError("Invalid local credential identifier")
        return entry_id

    @staticmethod
    def _decode(credential: "_CREDENTIALW", *, include_password: bool = False) -> dict:
        if credential.CredentialBlobSize > CRED_MAX_BLOB_SIZE:
            raise CredentialStoreError("Windows Credential Manager entry exceeds its supported size")
        raw = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
        try:
            entry = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CredentialStoreError("A saved local credential entry is malformed") from exc
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(key), str) for key in ("label", "username", "password", "notes")
        ):
            raise CredentialStoreError("A saved local credential entry has an unsupported format")
        if not include_password:
            entry.pop("password", None)
        return {"id": credential.TargetName, **entry}

    def list_entries(self) -> list[dict]:
        count = wintypes.DWORD()
        items = ctypes.POINTER(ctypes.POINTER(_CREDENTIALW))()
        pattern = TARGET_PREFIX + "*"
        if not self._api.CredEnumerateW(pattern, 0, ctypes.byref(count), ctypes.byref(items)):
            error = ctypes.get_last_error()
            if error == ERROR_NOT_FOUND:
                return []
            raise CredentialStoreError(f"Windows Credential Manager could not list entries (error {error})")
        try:
            rows = [self._decode(items[index].contents) for index in range(count.value)]
        finally:
            self._api.CredFree(items)
        rows.sort(key=lambda item: (item["label"].casefold(), item["username"].casefold()))
        return rows

    def read(self, entry_id: str) -> dict | None:
        target = self._target(entry_id)
        credential = ctypes.POINTER(_CREDENTIALW)()
        if not self._api.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(credential)):
            error = ctypes.get_last_error()
            if error == ERROR_NOT_FOUND:
                return None
            raise CredentialStoreError(f"Windows Credential Manager could not read an entry (error {error})")
        try:
            return self._decode(credential.contents, include_password=True)
        finally:
            self._api.CredFree(credential)

    def save(self, *, entry_id: str | None, label: str, username: str,
             password: str, notes: str) -> dict:
        if any(not isinstance(value, str) for value in (label, username, password, notes)):
            raise ValueError("Credential fields must be text")
        values = {"label": label.strip(), "username": username.strip(),
                  "password": password, "notes": notes}
        if not values["label"] or not values["password"]:
            raise ValueError("A service name and password are required")
        target = self._target(entry_id) if entry_id else TARGET_PREFIX + secrets.token_hex(16)
        blob = json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(blob) > CRED_MAX_BLOB_SIZE:
            raise ValueError("This entry is too large for Windows Credential Manager")
        credential = _CREDENTIALW()
        credential.Type = CRED_TYPE_GENERIC
        credential.TargetName = target
        credential.UserName = values["username"] or values["label"]
        credential.CredentialBlobSize = len(blob)
        credential._blob_buffer = ctypes.create_string_buffer(blob)
        credential.CredentialBlob = ctypes.cast(
            credential._blob_buffer, ctypes.POINTER(ctypes.c_ubyte)
        )
        credential.Persist = CRED_PERSIST_LOCAL_MACHINE
        if not self._api.CredWriteW(ctypes.byref(credential), 0):
            error = ctypes.get_last_error()
            raise CredentialStoreError(f"Windows Credential Manager could not save this entry (error {error})")
        return {"id": target, "label": values["label"], "username": values["username"],
                "notes": values["notes"]}

    def delete(self, entry_id: str) -> bool:
        target = self._target(entry_id)
        if self._api.CredDeleteW(target, CRED_TYPE_GENERIC, 0):
            return True
        error = ctypes.get_last_error()
        if error == ERROR_NOT_FOUND:
            return False
        raise CredentialStoreError(f"Windows Credential Manager could not delete an entry (error {error})")
