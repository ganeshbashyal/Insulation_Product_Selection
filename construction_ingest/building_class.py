"""Building-class construction profile ingestion (NCC 2022 Class 1-10).

Reads a stream of concatenated JSON objects describing per-class construction
stages and their insulation elements, normalises them, loads them into the local
SQLite database alongside the postcode/climate-zone tables, and exports local
LLM training artefacts.

Source shape
------------
The input is NOT a JSON array - it is a sequence of top-level ``{...}`` objects
separated by whitespace, and may contain LaTeX escapes (``\\ge``, ``$...$``)
that are invalid inside JSON strings. ``load_profiles`` repairs both.

    {
      "building_type": "Class 1a Single Dwelling Residential",
      "governing_code": "...",
      "applicable_standards": [...],
      "structural_system"|"structural_systems": ... ,
      "construction_stages": [
        {"stage_number": 1, "stage_name": "...", "trades": [...],
         "insulation_elements": [{"element": "...", "material": "...", ...}]}
      ]
    }

Insulation elements have a heterogeneous key set (``ncc_clause``, ``fire_rating``,
``acoustic_requirement``, ``thermal_performance``, ``material_class_zones_1_3``,
...). Known keys are promoted to columns; everything else is preserved verbatim
in an ``extra_json`` column so no source detail is lost.

Usage
-----
    python -m construction_ingest.building_class --source path/to/Buildingclassspecific.txt
    python -m construction_ingest.building_class --export-training
    python -m construction_ingest.building_class --lookup "Class 2"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

from construction_ingest.db_setup import DEFAULT_DB_PATH, connect

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "knowledge" / "building_classes" / "building_class_source.json"
DEFAULT_PROFILE_JSON = ROOT / "knowledge" / "building_classes" / "building_class_profiles.json"
TRAINING_DIR = ROOT / "knowledge" / "industry" / "training"

SYSTEM_PROMPT = (
    "You are an expert on Australian building construction and insulation: NCC 2022 "
    "building classifications, construction staging, AS/NZS standards, and where "
    "insulation, membranes and fire/acoustic materials are installed at each stage. "
    "You give specific, stage-aware answers, cite the NCC clause when the source "
    "states one, and flag when formal certification or a project-specific assessment "
    "is required."
)

SCOPE_NOTE = (
    "Screening and training aid only. Building classification is determined by the "
    "building surveyor/certifier, and fire, acoustic and energy requirements are "
    "project-specific. Not a compliance certificate."
)

#: Element keys promoted to their own SQLite column. Anything else is retained
#: in ``extra_json``.
PROMOTED_ELEMENT_KEYS = (
    "element",
    "material",
    "placement",
    "function",
    "ncc_clause",
    "fire_rating",
    "fire_compliance",
    "acoustic_requirement",
    "thermal_performance",
    "typical_specs",
)

#: Keys whose values are zone-conditional material selections.
ZONE_MATERIAL_KEYS = {
    "material_class_zones_1_3": (1, 3),
    "material_zones_1_3": (1, 3),
    "material_class_zones_4_8": (4, 8),
    "material_zones_4_8": (4, 8),
}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def repair_json_text(raw: str) -> str:
    """Strip LaTeX artefacts that make the source invalid JSON.

    The source embeds maths fragments such as ``$Rw + Ctr \\ge 50$`` inside
    string values. ``\\g`` is not a legal JSON escape, so the backslash is
    removed and the ``$`` delimiters are dropped, leaving readable prose.
    """
    # Convert LaTeX comparison macros first: stripping backslashes beforehand
    # would leave a bare "ge"/"le" that is indistinguishable from real prose.
    cleaned = raw
    for macro, symbol in (
        ("\\geq", ">="),
        ("\\leq", "<="),
        ("\\ge", ">="),
        ("\\le", "<="),
        ("\\neq", "!="),
        ("\\times", "x"),
        ("\\approx", "~"),
    ):
        cleaned = cleaned.replace(macro, symbol)
    # Drop any remaining backslash that does not begin a valid JSON escape.
    cleaned = re.sub(r'\\(?!["\\/bfnrtu])', "", cleaned)
    cleaned = re.sub(r"\$([^$\n]{0,120}?)\$", r"\1", cleaned)
    # Collapse the double spaces the delimiter removal can leave behind.
    return re.sub(r"[ \t]{2,}", " ", cleaned)


def iter_json_objects(raw: str) -> list[dict]:
    """Decode a JSON document that may be an array or concatenated objects."""
    decoder = json.JSONDecoder()
    objects: list[dict] = []
    index, length = 0, len(raw)
    while index < length:
        while index < length and raw[index] in " \t\r\n":
            index += 1
        if index >= length:
            break
        try:
            obj, index = decoder.raw_decode(raw, index)
        except json.JSONDecodeError as error:
            line = raw.count("\n", 0, error.pos) + 1
            raise ValueError(f"invalid JSON at line {line}: {error.msg}") from error
        if isinstance(obj, dict):
            objects.append(obj)
        elif isinstance(obj, list):
            objects.extend(item for item in obj if isinstance(item, dict))
    return objects


def extract_class_codes(building_type: str) -> list[str]:
    """Pull the NCC class codes out of a free-text building type.

    Handles single classes (``Class 1a``), lists (``Class 5 (Office) & Class 6``)
    and spans (``Class 2 to Class 9``). Returns canonical codes like ``1a``,
    ``9b``, ``10c``.
    """
    text = building_type or ""
    codes: list[str] = []

    span = re.search(r"class\s*(\d{1,2})\s*(?:to|-|–|through)\s*(?:class\s*)?(\d{1,2})", text, re.I)
    if span:
        low, high = int(span.group(1)), int(span.group(2))
        if 1 <= low <= high <= 10:
            codes.extend(str(n) for n in range(low, high + 1))

    for match in re.finditer(r"class\s*(\d{1,2})\s*([a-c])?(?![a-z])", text, re.I):
        number = int(match.group(1))
        if not 1 <= number <= 10:
            continue
        suffix = (match.group(2) or "").lower()
        code = f"{number}{suffix}"
        if code not in codes:
            codes.append(code)

    # A subclass makes its bare parent redundant ("Class 1a" implies class 1).
    subclassed = {code[:-1] for code in codes if code[-1].isalpha()}
    codes = [code for code in codes if not (code.isdigit() and code in subclassed)]
    return sorted(dict.fromkeys(codes), key=_class_sort_key)


def _class_sort_key(code: str) -> tuple[int, str]:
    match = re.match(r"(\d{1,2})([a-c]?)", code)
    return (int(match.group(1)), match.group(2)) if match else (99, code)


def primary_class(codes: list[str]) -> str:
    return codes[0] if codes else "unclassified"


def ncc_volume_for_classes(codes: list[str]) -> str:
    """Volume Two covers Class 1 and 10; Volume One covers Class 2-9."""
    numbers = {int(re.match(r"(\d{1,2})", code).group(1)) for code in codes if re.match(r"\d", code)}
    if not numbers:
        return "Unknown"
    vol_two = numbers <= {1, 10}
    vol_one = numbers <= set(range(2, 10))
    if vol_two:
        return "Vol 2 (ABCB Housing Provisions)"
    if vol_one:
        return "Vol 1"
    return "Vol 1 and Vol 2 (mixed classification)"


# ---------------------------------------------------------------------------
# Normalised model
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class InsulationElement:
    element: str
    material: str = ""
    placement: str = ""
    function: str = ""
    ncc_clause: str = ""
    fire_rating: str = ""
    fire_compliance: str = ""
    acoustic_requirement: str = ""
    thermal_performance: str = ""
    typical_specs: str = ""
    applicable_zones: list[int] = field(default_factory=list)
    zone_materials: dict[str, str] = field(default_factory=dict)
    extra: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "element": self.element,
            "material": self.material,
            "placement": self.placement,
            "function": self.function,
            "ncc_clause": self.ncc_clause,
            "fire_rating": self.fire_rating,
            "fire_compliance": self.fire_compliance,
            "acoustic_requirement": self.acoustic_requirement,
            "thermal_performance": self.thermal_performance,
            "typical_specs": self.typical_specs,
            "applicable_zones": self.applicable_zones,
            "zone_materials": self.zone_materials,
            "extra": self.extra,
        }


@dataclass(slots=True)
class ConstructionStage:
    stage_number: int
    stage_name: str
    trades: list[str] = field(default_factory=list)
    elements: list[InsulationElement] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "stage_number": self.stage_number,
            "stage_name": self.stage_name,
            "trades": self.trades,
            "insulation_elements": [element.as_dict() for element in self.elements],
        }


@dataclass(slots=True)
class BuildingClassProfile:
    profile_id: str
    building_type: str
    class_codes: list[str]
    primary_class: str
    ncc_volume: str
    governing_code: str = ""
    structural_systems: list[str] = field(default_factory=list)
    applicable_standards: list[str] = field(default_factory=list)
    stages: list[ConstructionStage] = field(default_factory=list)
    source_index: int = 0

    @property
    def element_count(self) -> int:
        return sum(len(stage.elements) for stage in self.stages)

    def as_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "building_type": self.building_type,
            "class_codes": self.class_codes,
            "primary_class": self.primary_class,
            "ncc_volume": self.ncc_volume,
            "governing_code": self.governing_code,
            "structural_systems": self.structural_systems,
            "applicable_standards": self.applicable_standards,
            "construction_stages": [stage.as_dict() for stage in self.stages],
        }


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)]


def _make_profile_id(building_type: str, index: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", building_type.casefold()).strip("-")[:60].strip("-")
    # The index is part of the digest so that two profiles sharing a building
    # type still receive distinct, stable ids.
    digest = hashlib.sha256(f"{building_type}|{index}".encode("utf-8")).hexdigest()[:8]
    return f"{slug or 'profile'}-{digest}" if slug else f"profile-{index}-{digest}"


def normalise_element(raw: dict) -> InsulationElement:
    """Promote known keys to fields and retain everything else in ``extra``."""
    zone_materials: dict[str, str] = {}
    extra: dict[str, object] = {}
    applicable_zones: list[int] = []

    for key, value in raw.items():
        if key in PROMOTED_ELEMENT_KEYS:
            continue
        if key in ZONE_MATERIAL_KEYS:
            low, high = ZONE_MATERIAL_KEYS[key]
            zone_materials[f"zones_{low}_{high}"] = str(value)
            continue
        if key == "applicable_zones":
            for item in _as_list(value):
                match = re.search(r"[1-8]", str(item))
                if match:
                    applicable_zones.append(int(match.group(0)))
            if isinstance(value, (list, tuple)):
                applicable_zones = [int(v) for v in value if isinstance(v, int) and 1 <= v <= 8] or applicable_zones
            continue
        extra[key] = value

    return InsulationElement(
        element=str(raw.get("element", "")).strip(),
        material=str(raw.get("material", "")).strip(),
        placement=str(raw.get("placement", "")).strip(),
        function=str(raw.get("function", "")).strip(),
        ncc_clause=str(raw.get("ncc_clause", "")).strip(),
        fire_rating=str(raw.get("fire_rating", "")).strip(),
        fire_compliance=str(raw.get("fire_compliance", "")).strip(),
        acoustic_requirement=str(raw.get("acoustic_requirement", "")).strip(),
        thermal_performance=str(raw.get("thermal_performance", "")).strip(),
        typical_specs=str(raw.get("typical_specs", "")).strip(),
        applicable_zones=sorted(set(applicable_zones)),
        zone_materials=zone_materials,
        extra=extra,
    )


def normalise_profile(raw: dict, index: int) -> BuildingClassProfile:
    building_type = str(raw.get("building_type", "")).strip() or f"Unnamed profile {index}"
    codes = extract_class_codes(building_type)

    systems = _as_list(raw.get("structural_systems")) or _as_list(raw.get("structural_system"))

    stages: list[ConstructionStage] = []
    for position, raw_stage in enumerate(raw.get("construction_stages") or [], start=1):
        if not isinstance(raw_stage, dict):
            continue
        try:
            number = int(raw_stage.get("stage_number", position))
        except (TypeError, ValueError):
            number = position
        stages.append(
            ConstructionStage(
                stage_number=number,
                stage_name=str(raw_stage.get("stage_name", "")).strip() or f"Stage {number}",
                trades=_as_list(raw_stage.get("trades")),
                elements=[
                    normalise_element(element)
                    for element in (raw_stage.get("insulation_elements") or [])
                    if isinstance(element, dict)
                ],
            )
        )
    stages.sort(key=lambda stage: stage.stage_number)

    return BuildingClassProfile(
        profile_id=_make_profile_id(building_type, index),
        building_type=building_type,
        class_codes=codes,
        primary_class=primary_class(codes),
        ncc_volume=ncc_volume_for_classes(codes),
        governing_code=str(raw.get("governing_code", "")).strip(),
        structural_systems=systems,
        applicable_standards=_as_list(raw.get("applicable_standards")),
        stages=stages,
        source_index=index,
    )


def load_profiles(source: Path | str) -> list[BuildingClassProfile]:
    """Read, repair, decode and normalise every profile in the source file."""
    path = Path(source)
    raw = path.read_text(encoding="utf-8", errors="replace")
    objects = iter_json_objects(repair_json_text(raw))
    return [normalise_profile(obj, index) for index, obj in enumerate(objects, start=1)]


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------

BUILDING_SCHEMA = """
CREATE TABLE IF NOT EXISTS building_class_profiles (
    profile_id          TEXT PRIMARY KEY,
    building_type       TEXT NOT NULL,
    primary_class       TEXT NOT NULL DEFAULT '',
    class_codes         TEXT NOT NULL DEFAULT '',
    ncc_volume          TEXT NOT NULL DEFAULT '',
    governing_code      TEXT NOT NULL DEFAULT '',
    structural_systems  TEXT NOT NULL DEFAULT '',
    applicable_standards TEXT NOT NULL DEFAULT '',
    stage_count         INTEGER NOT NULL DEFAULT 0,
    element_count       INTEGER NOT NULL DEFAULT 0,
    source_index        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS building_class_codes (
    profile_id  TEXT NOT NULL REFERENCES building_class_profiles(profile_id) ON DELETE CASCADE,
    class_code  TEXT NOT NULL,
    class_number INTEGER NOT NULL,
    PRIMARY KEY (profile_id, class_code)
);

CREATE TABLE IF NOT EXISTS building_class_stages (
    stage_uid    TEXT PRIMARY KEY,
    profile_id   TEXT NOT NULL REFERENCES building_class_profiles(profile_id) ON DELETE CASCADE,
    stage_number INTEGER NOT NULL,
    stage_name   TEXT NOT NULL,
    trades       TEXT NOT NULL DEFAULT '',
    element_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS building_class_elements (
    element_uid          TEXT PRIMARY KEY,
    stage_uid            TEXT NOT NULL REFERENCES building_class_stages(stage_uid) ON DELETE CASCADE,
    profile_id           TEXT NOT NULL REFERENCES building_class_profiles(profile_id) ON DELETE CASCADE,
    stage_number         INTEGER NOT NULL,
    stage_name           TEXT NOT NULL DEFAULT '',
    element              TEXT NOT NULL,
    material             TEXT NOT NULL DEFAULT '',
    placement            TEXT NOT NULL DEFAULT '',
    function             TEXT NOT NULL DEFAULT '',
    ncc_clause           TEXT NOT NULL DEFAULT '',
    fire_rating          TEXT NOT NULL DEFAULT '',
    fire_compliance      TEXT NOT NULL DEFAULT '',
    acoustic_requirement TEXT NOT NULL DEFAULT '',
    thermal_performance  TEXT NOT NULL DEFAULT '',
    typical_specs        TEXT NOT NULL DEFAULT '',
    applicable_zones     TEXT NOT NULL DEFAULT '',
    zone_materials_json  TEXT NOT NULL DEFAULT '{}',
    extra_json           TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_bc_codes_code ON building_class_codes (class_code);
CREATE INDEX IF NOT EXISTS idx_bc_codes_number ON building_class_codes (class_number);
CREATE INDEX IF NOT EXISTS idx_bc_stages_profile ON building_class_stages (profile_id);
CREATE INDEX IF NOT EXISTS idx_bc_elements_profile ON building_class_elements (profile_id);
CREATE INDEX IF NOT EXISTS idx_bc_elements_stage ON building_class_elements (stage_uid);
CREATE INDEX IF NOT EXISTS idx_bc_elements_clause ON building_class_elements (ncc_clause);

CREATE VIRTUAL TABLE IF NOT EXISTS building_class_search USING fts5(
    element, material, placement, function, ncc_clause, building_type, stage_name,
    element_uid UNINDEXED, profile_id UNINDEXED, tokenize = 'porter'
);

-- Shared with db_setup.py; declared here so this module can also seed a
-- standalone database that has not been through the postcode build.
CREATE TABLE IF NOT EXISTS build_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def create_building_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(BUILDING_SCHEMA)
    connection.commit()


def ingest_profiles(
    profiles: list[BuildingClassProfile],
    db_path: Path | str = DEFAULT_DB_PATH,
    replace: bool = True,
) -> dict:
    """Load normalised profiles into SQLite. Idempotent when ``replace`` is set."""
    connection = connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        create_building_schema(connection)
        if replace:
            for table in (
                "building_class_search",
                "building_class_elements",
                "building_class_stages",
                "building_class_codes",
                "building_class_profiles",
            ):
                connection.execute(f"DELETE FROM {table}")

        stage_rows = element_rows = code_rows = 0
        for profile in profiles:
            connection.execute(
                """
                INSERT OR REPLACE INTO building_class_profiles
                    (profile_id, building_type, primary_class, class_codes, ncc_volume,
                     governing_code, structural_systems, applicable_standards,
                     stage_count, element_count, source_index)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.profile_id,
                    profile.building_type,
                    profile.primary_class,
                    json.dumps(profile.class_codes),
                    profile.ncc_volume,
                    profile.governing_code,
                    json.dumps(profile.structural_systems),
                    json.dumps(profile.applicable_standards),
                    len(profile.stages),
                    profile.element_count,
                    profile.source_index,
                ),
            )
            for code in profile.class_codes:
                number = int(re.match(r"(\d{1,2})", code).group(1))
                connection.execute(
                    "INSERT OR REPLACE INTO building_class_codes (profile_id, class_code, class_number) VALUES (?, ?, ?)",
                    (profile.profile_id, code, number),
                )
                code_rows += 1

            for stage in profile.stages:
                stage_uid = f"{profile.profile_id}::s{stage.stage_number}"
                connection.execute(
                    """
                    INSERT OR REPLACE INTO building_class_stages
                        (stage_uid, profile_id, stage_number, stage_name, trades, element_count)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stage_uid,
                        profile.profile_id,
                        stage.stage_number,
                        stage.stage_name,
                        json.dumps(stage.trades),
                        len(stage.elements),
                    ),
                )
                stage_rows += 1

                for position, element in enumerate(stage.elements, start=1):
                    element_uid = f"{stage_uid}::e{position}"
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO building_class_elements
                            (element_uid, stage_uid, profile_id, stage_number, stage_name,
                             element, material, placement, function, ncc_clause,
                             fire_rating, fire_compliance, acoustic_requirement,
                             thermal_performance, typical_specs, applicable_zones,
                             zone_materials_json, extra_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            element_uid,
                            stage_uid,
                            profile.profile_id,
                            stage.stage_number,
                            stage.stage_name,
                            element.element,
                            element.material,
                            element.placement,
                            element.function,
                            element.ncc_clause,
                            element.fire_rating,
                            element.fire_compliance,
                            element.acoustic_requirement,
                            element.thermal_performance,
                            element.typical_specs,
                            json.dumps(element.applicable_zones),
                            json.dumps(element.zone_materials),
                            json.dumps(element.extra, ensure_ascii=False),
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO building_class_search
                            (element, material, placement, function, ncc_clause,
                             building_type, stage_name, element_uid, profile_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            element.element,
                            element.material,
                            element.placement,
                            element.function,
                            element.ncc_clause,
                            profile.building_type,
                            stage.stage_name,
                            element_uid,
                            profile.profile_id,
                        ),
                    )
                    element_rows += 1

        connection.executemany(
            "INSERT OR REPLACE INTO build_metadata (key, value) VALUES (?, ?)",
            [
                ("building_class_profiles", str(len(profiles))),
                ("building_class_stages", str(stage_rows)),
                ("building_class_elements", str(element_rows)),
                ("building_class_scope_note", SCOPE_NOTE),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    return {
        "profiles": len(profiles),
        "class_codes": code_rows,
        "stages": stage_rows,
        "elements": element_rows,
    }


# ---------------------------------------------------------------------------
# Query API
# ---------------------------------------------------------------------------


def normalise_class_code(value: str) -> str:
    """Turn ``"Class 9b"``, ``"9B"`` or ``"class-9b"`` into ``"9b"``."""
    match = re.search(r"(\d{1,2})\s*([a-cA-C])?", str(value or ""))
    if not match:
        return ""
    number = int(match.group(1))
    if not 1 <= number <= 10:
        return ""
    return f"{number}{(match.group(2) or '').lower()}"


def profiles_for_class(connection: sqlite3.Connection, class_code: str) -> list[dict]:
    """Return profiles matching a class code.

    A bare number (``"9"``) matches every subclass (``9a``, ``9b``, ``9c``);
    a specific subclass (``"9b"``) matches that subclass and any profile
    registered against the bare parent number.
    """
    code = normalise_class_code(class_code)
    if not code:
        return []
    number = int(re.match(r"(\d{1,2})", code).group(1))
    if code.isdigit():
        rows = connection.execute(
            """
            SELECT DISTINCT p.* FROM building_class_profiles p
            JOIN building_class_codes c ON c.profile_id = p.profile_id
            WHERE c.class_number = ?
            ORDER BY p.source_index
            """,
            (number,),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT DISTINCT p.* FROM building_class_profiles p
            JOIN building_class_codes c ON c.profile_id = p.profile_id
            WHERE c.class_code = ? OR c.class_code = ?
            ORDER BY p.source_index
            """,
            (code, str(number)),
        ).fetchall()

    results: list[dict] = []
    for row in rows:
        record = dict(row)
        record["class_codes"] = json.loads(record["class_codes"] or "[]")
        record["structural_systems"] = json.loads(record["structural_systems"] or "[]")
        record["applicable_standards"] = json.loads(record["applicable_standards"] or "[]")
        results.append(record)
    return results


def stages_for_profile(connection: sqlite3.Connection, profile_id: str) -> list[dict]:
    """Return every stage of a profile with its insulation elements."""
    stages: list[dict] = []
    for stage in connection.execute(
        "SELECT * FROM building_class_stages WHERE profile_id = ? ORDER BY stage_number",
        (profile_id,),
    ).fetchall():
        elements = [
            _element_row_to_dict(row)
            for row in connection.execute(
                "SELECT * FROM building_class_elements WHERE stage_uid = ? ORDER BY element_uid",
                (stage["stage_uid"],),
            ).fetchall()
        ]
        record = dict(stage)
        record["trades"] = json.loads(record["trades"] or "[]")
        record["insulation_elements"] = elements
        stages.append(record)
    return stages


def _element_row_to_dict(row: sqlite3.Row) -> dict:
    record = dict(row)
    record["applicable_zones"] = json.loads(record.get("applicable_zones") or "[]")
    record["zone_materials"] = json.loads(record.get("zone_materials_json") or "{}")
    record["extra"] = json.loads(record.get("extra_json") or "{}")
    record.pop("zone_materials_json", None)
    record.pop("extra_json", None)
    return record


def search_elements(connection: sqlite3.Connection, query: str, limit: int = 10) -> list[dict]:
    """Full-text search across insulation elements."""
    terms = re.findall(r"[A-Za-z0-9]+", query or "")
    if not terms:
        return []
    match_expression = " OR ".join(terms)
    try:
        rows = connection.execute(
            """
            SELECT e.* FROM building_class_search s
            JOIN building_class_elements e ON e.element_uid = s.element_uid
            WHERE building_class_search MATCH ?
            ORDER BY bm25(building_class_search) LIMIT ?
            """,
            (match_expression, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        like = f"%{terms[0]}%"
        rows = connection.execute(
            "SELECT * FROM building_class_elements WHERE element LIKE ? OR material LIKE ? LIMIT ?",
            (like, like, limit),
        ).fetchall()
    return [_element_row_to_dict(row) for row in rows]


def class_summary(connection: sqlite3.Connection) -> list[dict]:
    """Per-class coverage counts, for reporting and tests."""
    return [
        dict(row)
        for row in connection.execute(
            """
            SELECT c.class_code, c.class_number,
                   COUNT(DISTINCT p.profile_id) AS profiles,
                   SUM(p.element_count) AS elements
            FROM building_class_codes c
            JOIN building_class_profiles p ON p.profile_id = c.profile_id
            GROUP BY c.class_code, c.class_number
            ORDER BY c.class_number, c.class_code
            """
        ).fetchall()
    ]


# ---------------------------------------------------------------------------
# Training artefacts
# ---------------------------------------------------------------------------


def _element_sentence(element: InsulationElement) -> str:
    parts = [element.element]
    if element.material:
        parts.append(f"Material: {element.material}.")
    if element.placement:
        parts.append(f"Placement: {element.placement}.")
    if element.function:
        parts.append(f"Function: {element.function}.")
    if element.typical_specs:
        parts.append(f"Typical specification: {element.typical_specs}.")
    for label, value in (
        ("Thermal", element.thermal_performance),
        ("Acoustic", element.acoustic_requirement),
        ("Fire rating", element.fire_rating),
        ("Fire compliance", element.fire_compliance),
    ):
        if value:
            parts.append(f"{label}: {value}.")
    for zone_key, material in element.zone_materials.items():
        low, high = zone_key.replace("zones_", "").split("_")
        parts.append(f"Climate zones {low}-{high}: {material}.")
    if element.applicable_zones:
        parts.append(f"Applies in climate zones {', '.join(str(z) for z in element.applicable_zones)}.")
    for key, value in element.extra.items():
        parts.append(f"{key.replace('_', ' ').capitalize()}: {value}.")
    if element.ncc_clause:
        parts.append(f"Provision: {element.ncc_clause}.")
    return " ".join(part.rstrip(".") + "." if not part.endswith(".") else part for part in parts if part)


def _stage_text(profile: BuildingClassProfile, stage: ConstructionStage) -> str:
    header = (
        f"{profile.building_type} - stage {stage.stage_number}: {stage.stage_name}\n"
        f"NCC volume: {profile.ncc_volume}."
    )
    if profile.governing_code:
        header += f" Governing code: {profile.governing_code}."
    if stage.trades:
        header += f" Trades on site: {', '.join(stage.trades)}."
    if not stage.elements:
        return header + " No insulation or membrane elements are installed at this stage."
    body = "\n".join(f"- {_element_sentence(element)}" for element in stage.elements)
    return f"{header}\nInsulation and membrane elements at this stage:\n{body}"


def build_rag_chunks(profiles: list[BuildingClassProfile]) -> list[dict]:
    """One retrieval chunk per profile overview and per construction stage."""
    chunks: list[dict] = []
    for profile in profiles:
        overview = [
            f"{profile.building_type} - NCC 2022 construction overview.",
            f"NCC classes covered: {', '.join('Class ' + c for c in profile.class_codes) or 'unclassified'}.",
            f"Applicable NCC volume: {profile.ncc_volume}.",
        ]
        if profile.governing_code:
            overview.append(f"Governing code: {profile.governing_code}.")
        if profile.structural_systems:
            overview.append(f"Structural systems: {'; '.join(profile.structural_systems)}.")
        if profile.applicable_standards:
            overview.append(f"Applicable standards: {'; '.join(profile.applicable_standards)}.")
        if profile.stages:
            sequence = " -> ".join(f"{s.stage_number}. {s.stage_name}" for s in profile.stages)
            overview.append(f"Construction sequence: {sequence}.")
        text = " ".join(overview)
        chunks.append(
            {
                "chunk_id": f"BC-{profile.profile_id}-overview",
                "module_id": "building_class_profiles",
                "module_title": "NCC 2022 building-class construction profiles",
                "topic": profile.building_type,
                "kind": "overview",
                "building_class_codes": profile.class_codes,
                "ncc_volume": profile.ncc_volume,
                "text": text,
                "scope_note": SCOPE_NOTE,
                "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        )
        for stage in profile.stages:
            text = _stage_text(profile, stage)
            chunks.append(
                {
                    "chunk_id": f"BC-{profile.profile_id}-s{stage.stage_number}",
                    "module_id": "building_class_profiles",
                    "module_title": "NCC 2022 building-class construction profiles",
                    "topic": f"{profile.building_type} - {stage.stage_name}",
                    "kind": "construction_stage",
                    "building_class_codes": profile.class_codes,
                    "ncc_volume": profile.ncc_volume,
                    "stage_number": stage.stage_number,
                    "stage_name": stage.stage_name,
                    "trades": stage.trades,
                    "ncc_clauses": sorted({e.ncc_clause for e in stage.elements if e.ncc_clause}),
                    "text": text,
                    "scope_note": SCOPE_NOTE,
                    "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                }
            )
    return chunks


def _pair(question: str, answer: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
    }


def build_finetune_pairs(profiles: list[BuildingClassProfile]) -> list[dict]:
    """Chat-format Q&A pairs matching the repo's existing training convention."""
    pairs: list[dict] = []
    seen: set[str] = set()

    def add(question: str, answer: str) -> None:
        key = question.casefold()
        if key in seen or not answer.strip():
            return
        seen.add(key)
        pairs.append(_pair(question, answer))

    for profile in profiles:
        label = profile.building_type
        classes = ", ".join("Class " + c for c in profile.class_codes) or "an unclassified building"

        if profile.stages:
            sequence = " -> ".join(f"{s.stage_number}. {s.stage_name}" for s in profile.stages)
            add(
                f"What are the construction stages for {label}?",
                f"{label} covers {classes} under {profile.ncc_volume}. "
                f"The construction sequence is: {sequence}. {SCOPE_NOTE}",
            )

        if profile.applicable_standards:
            add(
                f"Which standards apply to {label}?",
                f"For {label} ({classes}), the source lists: "
                f"{'; '.join(profile.applicable_standards)}. "
                f"Governing code: {profile.governing_code or profile.ncc_volume}. {SCOPE_NOTE}",
            )

        if profile.structural_systems:
            add(
                f"What structural systems are typical for {label}?",
                f"{label} typically uses: {'; '.join(profile.structural_systems)}. {SCOPE_NOTE}",
            )

        for stage in profile.stages:
            if not stage.elements:
                continue
            elements = "\n".join(f"- {_element_sentence(element)}" for element in stage.elements)
            add(
                f"What insulation goes in at the {stage.stage_name} stage of {label}?",
                f"At stage {stage.stage_number} ({stage.stage_name}) of {label}, "
                f"the following are installed:\n{elements}\n{SCOPE_NOTE}",
            )
            if stage.trades:
                add(
                    f"Which trades are on site during the {stage.stage_name} stage of {label}?",
                    f"Stage {stage.stage_number} ({stage.stage_name}) of {label} involves: "
                    f"{', '.join(stage.trades)}.",
                )
            for element in stage.elements:
                if element.ncc_clause:
                    add(
                        f"Which NCC clause covers {element.element} in {label}?",
                        f"{element.element} in {label} is covered by {element.ncc_clause}. "
                        f"{_element_sentence(element)} {SCOPE_NOTE}",
                    )
                if element.placement:
                    add(
                        f"Where is {element.element} installed in {label}?",
                        f"{_element_sentence(element)} {SCOPE_NOTE}",
                    )
    return pairs


def _display_path(path: Path) -> str:
    """Repo-relative path where possible, absolute otherwise (e.g. temp dirs)."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def export_training_data(
    profiles: list[BuildingClassProfile],
    out_dir: Path | str = TRAINING_DIR,
) -> dict:
    """Write RAG chunks, fine-tune pairs and a build report."""
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)

    chunks = build_rag_chunks(profiles)
    pairs = build_finetune_pairs(profiles)

    chunk_path = directory / "building_class_rag_chunks.jsonl"
    pair_path = directory / "building_class_finetune.jsonl"
    report_path = directory / "building_class_training_report.json"

    for path, rows in ((chunk_path, chunks), (pair_path, pairs)):
        with open(path, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    report = {
        "generated_by": "construction_ingest/building_class.py",
        "system_prompt": SYSTEM_PROMPT,
        "scope_note": SCOPE_NOTE,
        "totals": {
            "profiles": len(profiles),
            "stages": sum(len(p.stages) for p in profiles),
            "elements": sum(p.element_count for p in profiles),
            "rag_chunks": len(chunks),
            "finetune_pairs": len(pairs),
        },
        "classes_covered": sorted(
            {code for profile in profiles for code in profile.class_codes}, key=_class_sort_key
        ),
        "outputs": {
            "rag_chunks_jsonl": _display_path(chunk_path),
            "finetune_jsonl": _display_path(pair_path),
        },
        "paths": {
            "rag_chunks_jsonl": chunk_path,
            "finetune_jsonl": pair_path,
            "report_json": report_path,
        },
    }
    report_path.write_text(
        json.dumps({k: v for k, v in report.items() if k != "paths"}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return report


def export_profiles_json(
    profiles: list[BuildingClassProfile], path: Path | str = DEFAULT_PROFILE_JSON
) -> Path:
    """Write the normalised profiles as a single tracked JSON document."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": "building_class_profiles/v1",
        "scope_note": SCOPE_NOTE,
        "profile_count": len(profiles),
        "classes_covered": sorted(
            {code for profile in profiles for code in profile.class_codes}, key=_class_sort_key
        ),
        "profiles": [profile.as_dict() for profile in profiles],
    }
    output.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
    return output


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="building-class JSON stream file")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database to update")
    parser.add_argument("--export-json", nargs="?", const=str(DEFAULT_PROFILE_JSON), help="write normalised profiles JSON")
    parser.add_argument("--export-training", action="store_true", help="write RAG chunks and fine-tune pairs")
    parser.add_argument("--training-dir", default=str(TRAINING_DIR), help="training output directory")
    parser.add_argument("--lookup", help="print the profiles for a class code, e.g. '9b'")
    parser.add_argument("--search", help="full-text search the ingested insulation elements")
    parser.add_argument("--summary", action="store_true", help="print per-class coverage")
    parser.add_argument("--no-ingest", action="store_true", help="parse only, do not touch SQLite")
    args = parser.parse_args(argv)

    source = Path(args.source)
    if not source.is_file():
        print(f"Source not found: {source}", file=sys.stderr)
        return 1

    try:
        profiles = load_profiles(source)
    except ValueError as error:
        print(f"Failed to parse {source}: {error}", file=sys.stderr)
        return 1
    print(f"Parsed {len(profiles)} building-class profiles from {source.name}")

    unclassified = [p.building_type for p in profiles if not p.class_codes]
    if unclassified:
        print(f"  ! {len(unclassified)} profile(s) had no detectable NCC class code", file=sys.stderr)

    if not args.no_ingest:
        stats = ingest_profiles(profiles, db_path=args.db)
        print(
            f"  ingested into {args.db}: {stats['profiles']} profiles, "
            f"{stats['stages']} stages, {stats['elements']} elements, "
            f"{stats['class_codes']} class-code links"
        )

    if args.export_json:
        path = export_profiles_json(profiles, args.export_json)
        print(f"  wrote normalised profiles to {path}")

    if args.export_training:
        report = export_training_data(profiles, args.training_dir)
        totals = report["totals"]
        print(
            f"  wrote {totals['rag_chunks']} RAG chunks and "
            f"{totals['finetune_pairs']} fine-tune pairs to {args.training_dir}"
        )
        print(f"  classes covered: {', '.join(report['classes_covered'])}")

    if args.summary or args.lookup or args.search:
        connection = connect(args.db)
        try:
            if args.summary:
                print("\nPer-class coverage:")
                for row in class_summary(connection):
                    print(f"  Class {row['class_code']:<4} {row['profiles']:>2} profile(s), {row['elements']:>4} elements")
            if args.lookup:
                found = profiles_for_class(connection, args.lookup)
                print(f"\n{len(found)} profile(s) for class {args.lookup}:")
                for record in found:
                    print(f"  [{record['profile_id']}] {record['building_type']}")
                    print(f"      {record['ncc_volume']} | {record['stage_count']} stages, {record['element_count']} elements")
            if args.search:
                results = search_elements(connection, args.search)
                print(f"\n{len(results)} element(s) matching '{args.search}':")
                for record in results[:10]:
                    print(f"  - {record['element']} (stage {record['stage_number']}: {record['stage_name']})")
                    if record["material"]:
                        print(f"      {record['material'][:110]}")
        finally:
            connection.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
