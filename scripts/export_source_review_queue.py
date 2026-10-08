"""Persist a private source review queue without downloads or model calls."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from source_review_queue import review_view
from tds_register import compiled_sources
from tds_build import save
from research_store import ResearchStore


def main():
    root = Path.cwd()
    pointer = json.loads((root / "data" / "local" / "tds_register.json").read_text())
    register = json.loads(Path(pointer["outputs"]["json"]).read_text())
    db = root / "data" / "local" / "product_research.sqlite3"
    history = ResearchStore(db).history() if db.is_file() else []
    queue = {key: review_view(compiled_sources(root, key), key, history)
             for key in register["families"]}
    output = Path(pointer["outputs"]["json"]).parent
    save(output / "source_review_queue.json", queue)
    lines = ["# Private source / variant review queue", "",
             "Collection frozen. Identity decisions do not bind documents or approve claims.", ""]
    for key, view in queue.items():
        lines.extend(["## " + key, ""])
        for item in view["items"]:
            lines.extend(["### " + item["kind"] + " / " + item["status"],
                          json.dumps(item, ensure_ascii=True, indent=2), ""])
    (output / "source_review_queue.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"families": len(queue), "items": sum(len(v["items"]) for v in queue.values()),
                      "output": str(output / "source_review_queue.md")}))


if __name__ == "__main__":
    main()
