"""Offline front door: shared reads and explicit named review/publication."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import getpass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge_service import KnowledgeService


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--root", type=Path, default=ROOT)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("overview")
    families = commands.add_parser("families")
    families.add_argument("--query", default="")
    families.add_argument("--limit", type=int, default=50)
    family = commands.add_parser("family")
    family.add_argument("family_id")
    commands.add_parser("validation")
    commands.add_parser("draft-preview")
    draft = commands.add_parser("draft-write")
    draft.add_argument("--confirm", required=True, help="exact all-family draft preview ID")
    draft_family = commands.add_parser("draft-family")
    draft_family.add_argument("family_id")
    status = commands.add_parser("draft-status")
    status.add_argument("batch")
    annotate = commands.add_parser("draft-annotate")
    annotate.add_argument("batch")
    annotate.add_argument("--limit", type=int, default=10, help="maximum sequential model tasks this invocation")
    annotate.add_argument("--retry", action="store_true", help="one explicit retry for a failed task")
    source = commands.add_parser("source-preview")
    source.add_argument("manifest", type=Path)
    stage = commands.add_parser("source-stage")
    stage.add_argument("manifest", type=Path)
    stage.add_argument("--confirm", required=True, help="exact source preview ID")
    for name in ("review", "retained-review"):
        review = commands.add_parser(name)
        review.add_argument("family_id")
        review.add_argument("input", type=Path)
        review.add_argument("--username", required=True)
        review.add_argument("--expected", type=int, default=0)
    publication = commands.add_parser("publication-preview")
    publication.add_argument("--username", required=True)
    publication.add_argument("--scoped", action="store_true")
    publish = commands.add_parser("publish")
    publish.add_argument("proposal_id", type=int)
    publish.add_argument("--username", required=True)
    publish.add_argument("--confirm", required=True, help="exact proposal ID")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    token = None
    store = None
    try:
        service = KnowledgeService(args.root)
        if hasattr(args, "username"):
            store = service.store()
            account = store.login(args.username, getpass.getpass("Named research password: "), "offline-cli")
            token = account["token"]
        if args.command == "overview":
            result = service.index().overview()
        elif args.command == "families":
            if args.limit < 1:
                raise ValueError("Limit must be positive")
            result = service.index().browse(query=args.query, limit=args.limit)
        elif args.command == "family":
            result = service.family(args.family_id)
        elif args.command == "draft-preview":
            result = service.draft_preview()
        elif args.command == "draft-write":
            result = service.draft_write(args.confirm)
        elif args.command == "draft-family":
            result = service.draft_family(args.family_id)
        elif args.command == "draft-status":
            result = service.draft_status(args.batch)
        elif args.command == "draft-annotate":
            result = service.draft_annotations(args.batch, args.limit, args.retry)
        elif args.command == "source-preview":
            result = service.source_preview(args.manifest)
        elif args.command == "source-stage":
            result = service.source_stage(args.manifest, args.confirm)
        elif args.command in {"review", "retained-review"}:
            method = service.review_claim_or_sku if args.command == "review" else service.review_retained
            data = json.loads(args.input.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict):
                raise ValueError("Review input must be a JSON object")
            result = method(args.family_id, data, args.username, args.expected)
        elif args.command == "publication-preview":
            result = service.publication_preview(args.username, scoped=args.scoped)
        elif args.command == "publish":
            if args.confirm != str(args.proposal_id):
                raise ValueError("Publication requires exact proposal ID confirmation")
            result = service.publish(args.proposal_id, args.username)
        else:
            result = service.validation()
        print(json.dumps(result, indent=2, default=str))
        return 0
    except (ValueError, OSError, EOFError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    finally:
        if token is not None:
            store.logout(token)


if __name__ == "__main__":
    raise SystemExit(main())
