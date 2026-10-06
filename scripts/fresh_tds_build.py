"""Versioned local TDS jobs; supplied-URL downloads are the only external step."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from product_research import ResearchIndex
from tds_build import Build


def verify_retention(build, index, family):
    actual = build.family(family, index)
    if actual["pack"]["dossier"] != index.detail(family)["dossier"]:
        raise ValueError("Original retained dossier differs from family draft; do not advance")
    for extraction in actual["pack"]["fresh_full_extraction"]:
        for page in extraction["pages"]:
            if page["text"] not in actual["readable"]:
                raise ValueError("Full source text missing from readable family draft; do not advance")


def work_one(build, index, build_id, family, budget):
    if not build.sources(build_id, family):
        pack = build.packs(build_id, index, family_id=family)
        verify_retention(build, index, family)
        report = build.report(build_id, index)
        return {"family_id": family, "calls": 0, "source_gap": True,
                "coverage": pack["processing_coverage"], "report": report}
    used = 0
    while used < budget:
        try:
            batch = build.model_batch(build_id, min(5, budget - used), family_id=family)
        except ValueError:
            build.packs(build_id, index, family_id=family)
            build.report(build_id, index)
            raise
        used += batch["calls_this_run"]
        pack = build.packs(build_id, index, family_id=family)
        verify_retention(build, index, family)
        report = build.report(build_id, index)
        print(json.dumps({"family_id": family, "calls_this_worker": used,
                          "coverage": pack["processing_coverage"], "report": report["path"]}), flush=True)
        if not pack["processing_coverage"]["pending_chunks"]:
            break
        if batch["calls_this_run"] == 0:
            raise ValueError("No model progress despite pending chunks; inspect receipts")
    return {"family_id": family, "calls": used, "coverage": pack["processing_coverage"], "report": report,
            "boundary": "Worker stops at this family; human review remains required"}


def work_alphabetical(build, index, build_id, budget, max_families):
    initial = build.report(build_id, index)
    report = json.loads(Path(initial["json"]).read_text(encoding="utf-8"))
    processed = []
    remaining = budget
    for row in report["families"]:
        if row["state"] in {"draft_with_source_gap", "draft_ready_for_human_review", "draft_ready_with_gaps"}:
            continue
        if row["state"] == "no_extractable_text" and row.get("draft_current"):
            continue
        result = work_one(build, index, build_id, row["family_id"], remaining)
        processed.append(result)
        remaining -= result["calls"]
        if len(processed) >= max_families or remaining <= 0:
            break
    return {"families_this_worker": len(processed), "calls": budget - remaining,
            "last_family": processed[-1]["family_id"] if processed else None,
            "report": build.report(build_id, index),
            "boundary": "Serial private draft processing only; no factual approval"}


def work_overnight(build, index, build_id, budget, max_batches):
    remaining = budget
    families = 0
    last = None
    for batch_number in range(1, max_batches + 1):
        last = work_alphabetical(build, index, build_id, remaining, 5)
        families += last["families_this_worker"]
        remaining -= last["calls"]
        print(json.dumps({"overnight_batch": batch_number, **last}), flush=True)
        if not last["families_this_worker"] or remaining <= 0:
            break
    return {"batches": batch_number, "families_processed": families, "calls": budget - remaining,
            "stop_reason": ("processing_exhausted" if not last["families_this_worker"]
                            else "call_budget" if remaining <= 0 else "batch_budget"),
            "report": last["report"],
            "boundary": "Five-family batches, serial local calls; final verification and human review still required"}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--cache", type=Path, required=True)
    sub = p.add_subparsers(dest="action", required=True)
    preview = sub.add_parser("preview")
    preview.add_argument("--workbook", type=Path, required=True)
    preview.add_argument("--extend-from", help="retain archived sources and receipts from this exact build")
    start = sub.add_parser("start")
    start.add_argument("--workbook", type=Path, required=True)
    start.add_argument("--confirm", required=True)
    start.add_argument("--extend-from", help="must match the additive preview")
    backup = sub.add_parser("backup")
    backup.add_argument("--target", type=Path, required=True)
    backup.add_argument("--confirm", action="store_true")
    run = sub.add_parser("run")
    run.add_argument("build_id")
    run.add_argument("--download-limit", type=int, default=10)
    run.add_argument("--model-limit", type=int, default=5)
    run.add_argument("--family", required=True, help="one exact family ID; no automatic next-family processing")
    work = sub.add_parser("work-family", help="bounded resumable worker; refresh report after each five local tasks")
    work.add_argument("build_id")
    work.add_argument("--family", required=True)
    work.add_argument("--max-calls", type=int, default=20, help="hard local model-call budget; never advances family")
    queue = sub.add_parser("work-alphabetical", help="serial family queue; validate each retained pack before advancing")
    queue.add_argument("build_id")
    queue.add_argument("--max-calls", type=int, default=20, help="hard TOTAL local model-call budget")
    queue.add_argument("--max-families", type=int, default=1)
    overnight = sub.add_parser("work-overnight", help="locally chain serial five-family batches; stop on first error")
    overnight.add_argument("build_id")
    overnight.add_argument("--max-calls", type=int, default=10000, help="hard TOTAL model-call budget")
    overnight.add_argument("--max-batches", type=int, default=60, help="hard five-family batch ceiling")
    for name in ("download", "extract", "model", "status", "packs", "report", "narrow-failed"):
        cmd = sub.add_parser(name)
        cmd.add_argument("build_id")
        if name not in {"status", "report"}:
            cmd.add_argument("--family", required=True, help="one exact family ID")
        if name == "report":
            cmd.add_argument("--links-workbook", type=Path,
                             help="include supplied TDS links from this workbook; links remain unverified")
            cmd.add_argument("--sku-inventory", type=Path,
                             help="include a local staff-release SKU inventory JSON")
        if name in {"download", "model"}:
            cmd.add_argument("--limit", type=int, default=5)
            cmd.add_argument("--retry", action="store_true", help="one explicit additional attempt; preserve failed receipt")
    args = p.parse_args(argv)
    try:
        build = Build(args.root, args.cache)
        if hasattr(args, "family") and args.family not in ResearchIndex(args.root).families:
            raise ValueError("Unknown family ID")
        if args.action in {"preview", "start"}:
            result = build.preview(args.workbook, ResearchIndex(args.root), extend_from=args.extend_from)
            if args.action == "start":
                result = build.start(result, args.confirm)
        elif args.action == "download":
            result = build.download(args.build_id, args.limit, retry=args.retry, family_id=args.family)
        elif args.action == "extract":
            result = build.extract(args.build_id, family_id=args.family)
        elif args.action == "model":
            result = build.model_batch(args.build_id, args.limit, retry=args.retry, family_id=args.family)
        elif args.action == "backup":
            if not args.confirm:
                raise ValueError("Desktop backup writes require --confirm")
            result = build.backup(args.target)
        elif args.action == "packs":
            result = build.packs(args.build_id, ResearchIndex(args.root), family_id=args.family)
            result["completion_report"] = build.report(args.build_id, ResearchIndex(args.root))
        elif args.action == "report":
            index = ResearchIndex(args.root)
            supplemental_links = None
            if args.links_workbook:
                preview = build.preview(args.links_workbook, index)
                supplemental_links = {
                    "workbook": preview["workbook"],
                    "sha256": preview["workbook_hash"],
                    "rows": preview["rows"],
                }
            supplemental_skus = None
            if args.sku_inventory:
                supplemental_skus = json.loads(args.sku_inventory.read_text(encoding="utf-8"))
            result = build.report(
                args.build_id, index, supplemental_links=supplemental_links,
                supplemental_skus=supplemental_skus,
            )
        elif args.action == "narrow-failed":
            result = build.narrow_failed(args.build_id, args.family)
        elif args.action == "work-family":
            if not 1 <= args.max_calls <= 10000:
                raise ValueError("Local worker call budget must be between 1 and 10000")
            result = work_one(build, ResearchIndex(args.root), args.build_id, args.family, args.max_calls)
        elif args.action in {"work-alphabetical", "work-overnight"}:
            ceiling = args.max_families if args.action == "work-alphabetical" else args.max_batches
            if not 1 <= args.max_calls <= 10000 or not 1 <= ceiling <= 1000:
                raise ValueError("Positive bounded call and family budgets required")
            index = ResearchIndex(args.root)
            if args.action == "work-overnight":
                result = work_overnight(build, index, args.build_id, args.max_calls, args.max_batches)
            else:
                result = work_alphabetical(build, index, args.build_id, args.max_calls, args.max_families)
        elif args.action == "run":
            build.download(args.build_id, args.download_limit, family_id=args.family)
            build.extract(args.build_id, family_id=args.family)
            try:
                build.model_batch(args.build_id, args.model_limit, family_id=args.family)
            except ValueError as exc:
                # Preserve readable retained packs with explicit incomplete model status.
                packs = build.packs(args.build_id, ResearchIndex(args.root), family_id=args.family)
                print(json.dumps({"error": str(exc), "private_partial_packs": packs}, indent=2))
                return 1
            result = build.packs(args.build_id, ResearchIndex(args.root), family_id=args.family)
        else:
            result = build.status(args.build_id)
        print(json.dumps(result, indent=2, ensure_ascii=True, default=str))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
