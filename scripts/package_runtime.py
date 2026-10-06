"""Build an allowlisted offline serving folder; excludes source libraries and live state."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from knowledge_release import ReleaseLibrary

FILES = (
    "web_agent.py","storefront_api.py","knowledge_release.py","release_exports.py","research_store.py",
    "agent_core.py","bot_engine.py","conversation_service.py","product_answers.py",
    "sku_catalogue.py","size_index.py","sales_brief.py","local_source_review.py",
    "enquiry_discovery.py","interaction_store.py","session_store.py","local_db.py",
    "auth_middleware.py","cors_validator.py","site_config.py","widget_config.py",
    "llm_client.py","router.py","policy_lint.py","retrieval_hygiene.py",
    "redis_support.py","requirements-runtime.txt",
    "config/matching.json","config/catalogue_states.json","config/persona.md",
    "knowledge/industry/training/01_glossary.md",
    "templates/widget.js","templates/storefront_chat.html","templates/sales_briefs.html",
    "scripts/runtime_backup.py","docs/LOCAL_DEPLOYMENT.md",
)

TOOL_FILES = (
    "tools/__init__.py","tools/base.py","tools/registry.py","tools/escalate.py",
    "tools/service_refusal.py","tools/commercial.py","tools/freight.py","tools/tracking.py",
)

LOCAL_OWNER_ONLY_EXCLUSIONS = (
    "oracle_api.py", "oracle_assistant.py", "oracle_store.py", "oracle_pricing.py",
    "templates/oracle.html", "data/local/oracle.sqlite3",
    "matrix_api.py", "neo_api.py", "neo_assistant.py", "neo_store.py",
    "templates/matrix.html", "templates/neo.html", "data/local/neo.sqlite3",
)


def package(root: Path, releases: Path, target: Path) -> dict:
    root,target=root.resolve(),target.resolve()
    allowed=(root/"data"/"local"/"distribution").resolve()
    if not allowed.is_relative_to(root) or not target.is_relative_to(allowed) or target==allowed or target.exists():
        raise ValueError("Use a new named directory under data/local/distribution")
    library=ReleaseLibrary(releases)
    release=library.active()
    paths=[root/name for name in (*FILES, *TOOL_FILES)]
    if any(not path.resolve().is_relative_to(root) or not path.is_file() for path in paths):
        raise ValueError("Required runtime input missing or outside checkout")
    outputs = [target / path.relative_to(root) for path in paths]
    outputs.extend([target / "releases" / (release["release_id"][:16] + ".json"),
                    target / "releases" / "active.json", target / "package_manifest.json"])
    if os.name == "nt" and any(len(str(path)) > 259 or len(str(path.parent)) > 247 for path in outputs):
        raise ValueError("Windows path budget exceeded; use a shorter package name or shorter checkout path. No package created.")
    target.mkdir(parents=True)
    hashes={}
    for source in paths:
        name=source.relative_to(root).as_posix()
        dest=target/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,dest)
        hashes[name]=hashlib.sha256(dest.read_bytes()).hexdigest()
    destination=target/"releases"
    snapshot=ReleaseLibrary(destination)
    snapshot.save(release)
    source_pointer=json.loads((library.directory/"active.json").read_text(encoding="utf-8"))
    if source_pointer["release_id"] != release["release_id"]:
        raise ValueError("Release changed during packaging; discard the partial named package")
    (destination/"active.json").write_text(json.dumps(source_pointer),encoding="utf-8")
    for source in destination.glob("*.json"):
        hashes[source.relative_to(target).as_posix()]=hashlib.sha256(source.read_bytes()).hexdigest()
    if set(LOCAL_OWNER_ONLY_EXCLUSIONS).intersection(path.relative_to(root).as_posix() for path in paths):
        raise ValueError("Owner-only Oracle resources must never enter the customer serving package")
    manifest={"release_id":release["release_id"],"files":hashes,"default_profile":"serving-only",
              "excluded":"site secrets, live databases, customer records, PDF/workbook originals, draft reviews, research routes, owner-only Oracle routes/prompts/conversations/notes/tasks, notebooks, model weights",
              "local_owner_only_exclusions":list(LOCAL_OWNER_ONLY_EXCLUSIONS)}
    (target/"package_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--releases",type=Path,required=True)
    parser.add_argument("--name",required=True)
    args=parser.parse_args()
    try:
        import re
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}",args.name):
            raise ValueError("Simple named package ID required")
        target=ROOT/"data"/"local"/"distribution"/args.name
        result=package(ROOT,args.releases,target)
        print(json.dumps({"package":str(target),"release_id":result["release_id"],"file_count":len(result["files"])},indent=2))
        return 0
    except (OSError,ValueError,KeyError) as exc:
        print(f"Packaging blocked: {exc}",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
