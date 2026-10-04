"""Create/disable named local research accounts; passwords never enter CLI args."""
import argparse
import getpass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_store import ResearchStore, ROLES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "disable", "enable"])
    parser.add_argument("username")
    parser.add_argument("--roles", nargs="+", choices=sorted(ROLES), default=["reader"])
    args = parser.parse_args()
    store = ResearchStore()
    if args.action == "create":
        password = getpass.getpass("Password (at least 14 characters): ")
        if password != getpass.getpass("Confirm password: "):
            raise SystemExit("Passwords do not match; no account created")
        store.create_user(args.username, password, args.roles)
    else:
        store.set_disabled(args.username, args.action == "disable")
    print("Local account updated; no credential displayed.")


if __name__ == "__main__":
    main()
