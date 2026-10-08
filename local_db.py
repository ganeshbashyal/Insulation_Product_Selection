"""Consistent SQLite connection policy for local application stores."""
from __future__ import annotations

import sqlite3
import os
from pathlib import Path

BUSY_TIMEOUT_MS = 5000


def state_path(name: str) -> Path:
    return Path(os.getenv("AURORA_STATE_DIR", str(Path(__file__).resolve().parent / "data" / "local"))) / name


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000)
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection
