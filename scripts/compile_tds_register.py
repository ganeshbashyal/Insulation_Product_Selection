"""Compile frozen cache evidence without downloading or approving anything."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from product_research import ResearchIndex
from tds_build import Build
from tds_register import compile_register


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build_id")
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    build = Build(Path.cwd(), args.cache)
    with build.lock():
        pointer = compile_register(build, args.build_id, ResearchIndex(Path.cwd()))
    report = build.report(args.build_id, ResearchIndex(Path.cwd()))
    print(json.dumps({"register": pointer["outputs"], "report": report["workspace_report"]}))


if __name__ == "__main__":
    main()
