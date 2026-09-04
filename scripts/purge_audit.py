"""Apply the configured review retention deadlines to the local audit database."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audit_store import DEFAULT_DB, purge_expired  # noqa: E402

if __name__ == "__main__":
    print(f"Purged expired reviews: {purge_expired(DEFAULT_DB)}")
