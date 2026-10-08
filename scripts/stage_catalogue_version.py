"""Explicit new-code catalogue preview, staging and owner-confirmed activation."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from catalogue_versions import CatalogueLibrary, preview


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    parser.add_argument("--mapping",type=Path,required=True)
    parser.add_argument("--sheet")
    parser.add_argument("--stage",action="store_true")
    parser.add_argument("--activate",action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument("--expected-active")
    args=parser.parse_args()
    try:
        data=preview(ROOT,args.source,json.loads(args.mapping.read_text(encoding="utf-8-sig")),args.sheet)
        library=CatalogueLibrary(ROOT)
        if args.activate:
            if args.stage:
                raise ValueError("Stage and activate are separate actions")
            if library.read(data["version_id"])!=data:
                raise ValueError("Source/mapping changed after staging")
            library.activate(data["version_id"],args.confirm,args.expected_active)
            print(json.dumps({"active_version":data["version_id"],"new_eligibility":"held"}))
        elif args.stage:
            if args.confirm!=data["version_id"]:
                raise ValueError("Confirm exact preview version ID to stage")
            print(json.dumps({"staged":str(library.stage(data))}))
        else:
            print(json.dumps(data,indent=2,default=str))
        return 0
    except (OSError,ValueError,KeyError) as exc:
        print(f"Catalogue blocked: {exc}",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
