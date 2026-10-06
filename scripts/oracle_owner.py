"""Create or reset the dedicated Oracle owner passphrase interactively."""
from __future__ import annotations

import argparse
import getpass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from oracle_store import OracleStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true",
                        help="replace the configured passphrase and invalidate all Oracle sessions")
    args = parser.parse_args()
    store = OracleStore()
    if store.configured() and not args.reset:
        parser.error("Oracle is already configured; pass --reset to replace the owner passphrase")
    if not store.configured() and args.reset:
        parser.error("Oracle has not been configured; omit --reset for initial setup")
    first = getpass.getpass("New Oracle owner passphrase (14-256 characters): ")
    second = getpass.getpass("Confirm Oracle owner passphrase: ")
    if first != second:
        parser.error("Passphrases do not match")
    try:
        store.set_passphrase(first, reset=args.reset)
    except ValueError as exc:
        parser.error(str(exc))
    print("Oracle owner passphrase configured locally.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
