"""Build a local SQLite catalogue from the repo's family metadata and research JSON.

This creates the structured product layer the bot can query directly for:
- family metadata
- variant/range data
- installation and clearances
- product lookup by thickness/width/R-value

It deliberately does not replace the markdown knowledge layer; it complements it.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = value.replace("&", "and")
    value = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value)
    value = "-".join(part for part in value.split("-") if part)
    return value or "family"


def _read_json(path: Path):
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _coerce_int(value):
    try:
        return int(float(str(value).replace(",", "").replace("mm", "").strip()))
    except (TypeError, ValueError):
        return None


def _normalise_header(value: str) -> str:
    return str(value).casefold().replace("-", "").replace("_", "").replace(" ", "")


def _find_header_index(headers, *fragments: str) -> int | None:
    for index, header in enumerate(headers or []):
        normalised = _normalise_header(header)
        if all(fragment.casefold().replace("-", "").replace("_", "").replace(" ", "") in normalised for fragment in fragments):
            return index
    return None


def _research_path_for_family(research_dir: Path, family_id: str, family_name: str) -> Path | None:
    candidates: list[Path] = []
    if family_name:
        direct_variants = {
            family_name,
            family_name.strip().lower(),
            slugify(family_name),
            slugify(family_name).replace("-", "_"),
            slugify(family_name).replace("_", "-"),
        }
        for variant in sorted(direct_variants):
            candidates.append(research_dir / f"{variant}.json")
            candidates.append(research_dir / f"{variant.replace('-', '_')}.json")
            candidates.append(research_dir / f"{variant.replace('_', '-')}.json")
    if family_id:
        family_id_variants = {
            family_id,
            family_id.strip().lower(),
            slugify(family_id),
            slugify(family_id).replace("-", "_"),
            slugify(family_id).replace("_", "-"),
        }
        for variant in sorted(family_id_variants):
            candidates.append(research_dir / f"{variant}.json")
            candidates.append(research_dir / f"{variant.replace('-', '_')}.json")
            candidates.append(research_dir / f"{variant.replace('_', '-')}.json")

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists():
            return candidate

    for path in sorted(research_dir.glob("*.json")):
        data = _read_json(path)
        if not data:
            continue
        if family_id and str(data.get("family_id", "")).upper() == str(family_id).upper():
            return path
        if family_name and str(data.get("family_name", "")).casefold() == str(family_name).casefold():
            return path

    return None


def build_database(root: Path = ROOT, db_path: Path | None = None) -> Path:
    if db_path is None:
        db_path = root / "data" / "local" / "family_catalogue.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            DROP TABLE IF EXISTS family_installation;
            DROP TABLE IF EXISTS family_variants;
            DROP TABLE IF EXISTS families;

            CREATE TABLE families (
                family_id TEXT PRIMARY KEY,
                manufacturer TEXT NOT NULL,
                family_name TEXT NOT NULL,
                category TEXT,
                primary_function TEXT,
                applications_json TEXT,
                keywords_json TEXT,
                knowledge_file TEXT,
                source_url TEXT,
                confidence TEXT,
                detailed_knowledge_status TEXT,
                family_slug TEXT
            );

            CREATE TABLE family_variants (
                family_id TEXT NOT NULL,
                row_index INTEGER NOT NULL,
                r_value TEXT,
                thickness_mm INTEGER,
                width_mm INTEGER,
                length_mm INTEGER,
                product_code TEXT,
                coverage_m2 REAL,
                packs_per_bale INTEGER,
                FOREIGN KEY(family_id) REFERENCES families(family_id)
            );

            CREATE TABLE family_installation (
                family_id TEXT NOT NULL,
                row_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                category TEXT,
                FOREIGN KEY(family_id) REFERENCES families(family_id)
            );
            """
        )

        families_seen: set[str] = set()
        for families_path in sorted(root.glob("knowledge/*/families.json")):
            data = _read_json(families_path)
            if not data or "families" not in data:
                continue
            manufacturer = families_path.parent.name.title()
            for family in data["families"]:
                family_id = family.get("family_id")
                if not family_id or family_id in families_seen:
                    continue
                families_seen.add(family_id)
                family_name = family.get("name", "")
                connection.execute(
                    "INSERT INTO families (family_id, manufacturer, family_name, category, primary_function, applications_json, keywords_json, knowledge_file, source_url, confidence, detailed_knowledge_status, family_slug) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        family_id,
                        family.get("manufacturer", manufacturer),
                        family_name,
                        family.get("category"),
                        family.get("primary_function"),
                        json.dumps(family.get("applications", []), ensure_ascii=False),
                        json.dumps(family.get("keywords", []), ensure_ascii=False),
                        family.get("knowledge_file"),
                        family.get("source_url"),
                        family.get("confidence"),
                        family.get("detailed_knowledge_status"),
                        slugify(family_name),
                    ),
                )

                research_path = _research_path_for_family(families_path.parent / "research", family_id, family_name)
                research = _read_json(research_path)
                if not research or not isinstance(research.get("spec"), dict):
                    continue
                spec = research["spec"]
                headers = spec.get("range_headers") or []
                rows = spec.get("range") or []
                for idx, row in enumerate(rows):
                    if not isinstance(row, dict):
                        continue
                    r_index = _find_header_index(headers, "r")
                    if r_index is None:
                        r_value = str(row.get("c0", "")).strip()
                    else:
                        r_value = str(row.get(f"c{r_index}", "")).strip()
                    thickness = None
                    width = None
                    length = None
                    product_code = ""
                    coverage = None
                    packs_per_bale = None
                    if headers:
                        for i, header in enumerate(headers):
                            value = str(row.get(f"c{i}", "")).strip()
                            key = _normalise_header(header)
                            if "rvalue" in key:
                                r_value = value
                            elif "thickness" in key:
                                thickness = _coerce_int(value)
                            elif "width" in key:
                                width = _coerce_int(value)
                            elif "length" in key:
                                length = _coerce_int(value)
                            elif "code" in key:
                                product_code = value
                            elif "coverage" in key and "m2" in key:
                                try:
                                    coverage = float(value)
                                except ValueError:
                                    coverage = None
                            elif "bale" in key:
                                packs_per_bale = _coerce_int(value)
                    else:
                        if row:
                            values = list(row.values())
                            if values:
                                r_value = str(values[0]).strip()
                                thickness = _coerce_int(values[1]) if len(values) > 1 else None
                                width = _coerce_int(values[2]) if len(values) > 2 else None
                                product_code = str(values[-1]).strip() if len(values) > 0 else ""

                    connection.execute(
                        "INSERT INTO family_variants (family_id, row_index, r_value, thickness_mm, width_mm, length_mm, product_code, coverage_m2, packs_per_bale) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            family_id,
                            idx,
                            r_value,
                            thickness,
                            width,
                            length,
                            product_code,
                            coverage,
                            packs_per_bale,
                        ),
                    )

                for idx, step in enumerate(spec.get("install") or []):
                    if not str(step).strip():
                        continue
                    connection.execute(
                        "INSERT INTO family_installation (family_id, row_index, text, category) VALUES (?, ?, ?, 'install')",
                        (family_id, idx, str(step).strip()),
                    )
                for idx, item in enumerate(spec.get("clearances") or []):
                    if not str(item).strip():
                        continue
                    connection.execute(
                        "INSERT INTO family_installation (family_id, row_index, text, category) VALUES (?, ?, ?, 'clearance')",
                        (family_id, idx, str(item).strip()),
                    )
                for idx, item in enumerate(spec.get("limitations") or []):
                    if not str(item).strip():
                        continue
                    connection.execute(
                        "INSERT INTO family_installation (family_id, row_index, text, category) VALUES (?, ?, ?, 'limitation')",
                        (family_id, idx, str(item).strip()),
                    )

    return db_path


def main() -> None:
    build_database()


if __name__ == "__main__":
    main()
