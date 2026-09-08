"""Build the local postcode -> ABCB/NCC climate zone SQLite database.

Zero cloud cost: the only network call is an optional plain ``urllib`` download
of a public open-data CSV. With no network the database still builds from the
bundled range seed, so the pipeline is always runnable offline.

Provenance model
----------------
Every row carries a ``source`` and a ``confidence`` column, because the two
available data qualities are very different:

``authoritative``
    Loaded from a supplied postcode/climate-zone CSV (ABCB climate zone table
    or the NatHERS/ABCB postcode list). Suburb-level, cite-able.

``range_seed``
    Derived from the bundled coarse postcode-range table in this module. It is
    a *screening default only*. Climate-zone boundaries do not follow postcode
    boundaries, so a range seed must never be presented as the project's zone.

Usage
-----
    python -m construction_ingest.db_setup --db data/construction_postcodes.db
    python -m construction_ingest.db_setup --csv path/to/abcb_climate_zones.csv
    python -m construction_ingest.db_setup --url https://example.gov.au/zones.csv
    python -m construction_ingest.db_setup --export-json data/postcode_zones.json
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "construction_postcodes.db"
DEFAULT_JSON_PATH = ROOT / "data" / "postcode_zones.json"
DOWNLOAD_TIMEOUT_SECONDS = 30

#: Optional public sources. Neither is guaranteed to stay at a fixed URL, so a
#: failed download is a warning, never a hard error - the range seed still
#: produces a usable database.
PUBLIC_SOURCES = (
    "https://raw.githubusercontent.com/matthewproctor/australianpostcodes/master/australian_postcodes.csv",
)

VALID_ZONES = frozenset(range(1, 9))

STATES = ("NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT")


@dataclass(frozen=True, slots=True)
class PostcodeZone:
    """One postcode/locality row in the climate-zone lookup."""

    postcode: str
    suburb: str
    state: str
    climate_zone: int
    ncc_volume: str
    source: str
    confidence: str

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# NCC volume
# ---------------------------------------------------------------------------

NCC_VOLUME_NOTE = (
    "NCC volume follows the building classification, not the postcode. "
    "Volume Two (and the ABCB Housing Provisions) covers Class 1 and Class 10 "
    "buildings; Volume One covers Class 2-9. Both apply nationally, so this "
    "field records the residential default used for screening."
)

#: Residential screening default. A Class 2 apartment block in the same
#: postcode is a Volume One job - the caller must confirm the class.
DEFAULT_NCC_VOLUME = "Vol 2 (Class 1 & 10 - ABCB Housing Provisions); Vol 1 if Class 2-9"


def ncc_volume_for(building_class: str | None = None) -> str:
    """Return the applicable NCC 2022 volume for a building classification."""
    if not building_class:
        return DEFAULT_NCC_VOLUME
    text = str(building_class).strip().casefold().replace("class", "").strip()
    match = re.match(r"(\d+)", text)
    if not match:
        return DEFAULT_NCC_VOLUME
    number = int(match.group(1))
    if number in (1, 10):
        return "Vol 2 (ABCB Housing Provisions)"
    if 2 <= number <= 9:
        return "Vol 1"
    return DEFAULT_NCC_VOLUME


# ---------------------------------------------------------------------------
# Bundled coarse range seed
# ---------------------------------------------------------------------------

#: ``(low, high, state, zone, label)`` inclusive postcode ranges.
#:
#: Deliberately coarse and conservative: it exists so the engine has a complete
#: 4-digit lookup offline. Where a range spans several real zones the entry
#: takes the dominant zone for the populated part of the range and is always
#: flagged ``range_seed`` so downstream code can demand confirmation.
POSTCODE_RANGE_SEED: tuple[tuple[int, int, str, int, str], ...] = (
    # --- NSW / ACT ---------------------------------------------------------
    (1000, 1999, "NSW", 5, "Sydney business/PO boxes"),
    (2000, 2249, "NSW", 5, "Sydney metro and eastern suburbs"),
    (2250, 2299, "NSW", 5, "Central Coast and Newcastle"),
    (2300, 2339, "NSW", 5, "Hunter"),
    (2340, 2399, "NSW", 4, "New England and north-west slopes"),
    (2400, 2490, "NSW", 4, "Northern inland NSW"),
    (2500, 2579, "NSW", 6, "Illawarra and Southern Highlands"),
    (2580, 2599, "NSW", 7, "Southern Tablelands"),
    (2600, 2618, "ACT", 7, "Canberra central and inner suburbs"),
    (2619, 2620, "NSW", 7, "Queanbeyan and ACT fringe"),
    (2621, 2739, "NSW", 6, "South-east and Riverina fringe"),
    (2740, 2786, "NSW", 6, "Blue Mountains and western Sydney fringe"),
    (2787, 2879, "NSW", 4, "Central west and far west NSW"),
    (2880, 2899, "NSW", 4, "Broken Hill and far west"),
    (2900, 2920, "ACT", 7, "Canberra"),
    # --- NT ----------------------------------------------------------------
    (800, 832, "NT", 1, "Darwin and Top End"),
    (833, 861, "NT", 3, "Katherine and Barkly"),
    (862, 899, "NT", 3, "Alice Springs and central Australia"),
    # --- VIC ---------------------------------------------------------------
    (3000, 3207, "VIC", 6, "Melbourne metro"),
    (3208, 3334, "VIC", 6, "Geelong, Bellarine and western Melbourne fringe"),
    (3335, 3399, "VIC", 6, "Ballarat corridor"),
    (3400, 3499, "VIC", 4, "Wimmera and Mallee"),
    (3500, 3599, "VIC", 4, "Mildura and north-west Victoria"),
    (3600, 3699, "VIC", 4, "Goulburn Valley and northern Victoria"),
    (3700, 3749, "VIC", 7, "North-east Victoria and alpine approaches"),
    (3750, 3799, "VIC", 6, "Outer north-east Melbourne"),
    (3800, 3879, "VIC", 6, "Gippsland"),
    (3880, 3909, "VIC", 6, "East Gippsland"),
    (3910, 3999, "VIC", 6, "Mornington Peninsula and Westernport"),
    # --- QLD ---------------------------------------------------------------
    (4000, 4207, "QLD", 2, "Brisbane metro"),
    (4208, 4287, "QLD", 2, "Gold Coast and hinterland"),
    (4288, 4399, "QLD", 5, "Darling Downs and Toowoomba"),
    (4400, 4499, "QLD", 5, "Toowoomba region"),
    (4500, 4579, "QLD", 2, "Moreton Bay and Sunshine Coast"),
    (4580, 4699, "QLD", 2, "Wide Bay and Fraser Coast"),
    (4700, 4749, "QLD", 3, "Rockhampton and central Queensland"),
    (4750, 4805, "QLD", 3, "Mackay and Whitsunday"),
    (4806, 4849, "QLD", 1, "Townsville and Burdekin"),
    (4850, 4899, "QLD", 1, "Cairns and far north Queensland"),
    (4900, 4999, "QLD", 3, "Central-west and outback Queensland"),
    # --- SA ----------------------------------------------------------------
    (5000, 5199, "SA", 5, "Adelaide metro"),
    (5200, 5299, "SA", 6, "Adelaide Hills and Fleurieu"),
    (5300, 5399, "SA", 4, "Murraylands and Riverland"),
    (5400, 5499, "SA", 4, "Mid North"),
    (5500, 5599, "SA", 4, "Yorke Peninsula and Barossa fringe"),
    (5600, 5699, "SA", 4, "Eyre Peninsula and Spencer Gulf"),
    (5700, 5799, "SA", 4, "Far north SA"),
    (5800, 5999, "SA", 5, "Adelaide business/PO boxes"),
    # --- WA ----------------------------------------------------------------
    (6000, 6199, "WA", 5, "Perth metro"),
    (6200, 6299, "WA", 5, "Peel and outer Perth"),
    (6300, 6399, "WA", 5, "Great Southern and Albany"),
    (6400, 6499, "WA", 4, "Wheatbelt"),
    (6500, 6629, "WA", 4, "Midwest and Geraldton corridor"),
    (6630, 6699, "WA", 4, "Murchison and Gascoyne"),
    (6700, 6799, "WA", 1, "Pilbara and Kimberley"),
    (6800, 6999, "WA", 5, "Perth business/PO boxes"),
    # --- TAS ---------------------------------------------------------------
    (7000, 7099, "TAS", 7, "Hobart and southern Tasmania"),
    (7100, 7199, "TAS", 7, "Southern and midlands Tasmania"),
    (7200, 7299, "TAS", 7, "Launceston and northern Tasmania"),
    (7300, 7499, "TAS", 7, "North-west Tasmania"),
    (7500, 7999, "TAS", 7, "Tasmania (other)"),
)

#: Postcodes that sit wholly (or overwhelmingly) in alpine zone 8. These take
#: precedence over the coarse ranges above, which would otherwise return the
#: surrounding zone 6/7.
ALPINE_POSTCODES: dict[str, tuple[str, str]] = {
    "2624": ("NSW", "Perisher Valley / Charlotte Pass / Smiggin Holes"),
    "2625": ("NSW", "Thredbo Village"),
    "3898": ("VIC", "Dinner Plain"),
}

#: Named alpine/high-country localities that sit in zone 8 inside a postcode
#: range whose dominant zone is lower. Matched on suburb text when the source
#: data provides suburb names.
ALPINE_SUBURB_HINTS: tuple[tuple[str, str], ...] = (
    ("VIC", "falls creek"),
    ("VIC", "mount hotham"),
    ("VIC", "mount buller"),
    ("VIC", "dinner plain"),
    ("VIC", "mount baw baw"),
    ("NSW", "thredbo"),
    ("NSW", "perisher"),
    ("NSW", "charlotte pass"),
    ("NSW", "cabramurra"),
    ("NSW", "smiggin holes"),
)

ZONE_DESCRIPTIONS: dict[int, str] = {
    1: "High humidity summer, warm winter",
    2: "Warm humid summer, mild winter",
    3: "Hot dry summer, warm winter",
    4: "Hot dry summer, cool winter",
    5: "Warm temperate",
    6: "Mild temperate",
    7: "Cool temperate",
    8: "Alpine",
}


def zone_for_postcode(postcode: str | int, suburb: str = "", state: str = "") -> tuple[int | None, str, str]:
    """Return ``(zone, state, range_label)`` from the bundled range seed."""
    code = normalise_postcode(postcode)
    if code is None:
        return None, state.upper(), ""
    number = int(code)
    suburb_key = (suburb or "").casefold().strip()
    if code in ALPINE_POSTCODES:
        seed_state, label = ALPINE_POSTCODES[code]
        return 8, seed_state, f"Alpine postcode ({label})"
    for seed_state, hint in ALPINE_SUBURB_HINTS:
        if suburb_key and hint in suburb_key:
            return 8, seed_state, f"Alpine locality ({hint})"
    for low, high, seed_state, zone, label in POSTCODE_RANGE_SEED:
        if low <= number <= high:
            return zone, seed_state, label
    return None, state.upper(), ""


def normalise_postcode(value: str | int | None) -> str | None:
    """Coerce a value to a zero-padded 4-digit Australian postcode string."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"\b(\d{3,4})\b", text)
    if not match:
        return None
    code = match.group(1).zfill(4)
    if not 200 <= int(code) <= 9999:
        return None
    return code


def coerce_zone(value: object) -> int | None:
    """Parse a climate-zone value such as ``"Zone 6"``, ``"6"`` or ``6``."""
    if value is None:
        return None
    match = re.search(r"[1-8]", str(value))
    if not match:
        return None
    zone = int(match.group(0))
    return zone if zone in VALID_ZONES else None


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS postcode_zones (
    postcode      TEXT NOT NULL,
    suburb        TEXT NOT NULL DEFAULT '',
    state         TEXT NOT NULL DEFAULT '',
    climate_zone  INTEGER NOT NULL CHECK (climate_zone BETWEEN 1 AND 8),
    ncc_volume    TEXT NOT NULL DEFAULT '',
    source        TEXT NOT NULL DEFAULT 'range_seed',
    confidence    TEXT NOT NULL DEFAULT 'range_seed'
        CHECK (confidence IN ('authoritative', 'range_seed')),
    PRIMARY KEY (postcode, suburb, state)
);

CREATE INDEX IF NOT EXISTS idx_postcode ON postcode_zones (postcode);
CREATE INDEX IF NOT EXISTS idx_postcode_zone ON postcode_zones (climate_zone);
CREATE INDEX IF NOT EXISTS idx_postcode_state ON postcode_zones (state);
CREATE INDEX IF NOT EXISTS idx_postcode_suburb ON postcode_zones (suburb);

CREATE TABLE IF NOT EXISTS climate_zones (
    climate_zone INTEGER PRIMARY KEY CHECK (climate_zone BETWEEN 1 AND 8),
    description  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS build_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open the climate-zone database with row access by column name."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    connection.executemany(
        "INSERT OR REPLACE INTO climate_zones (climate_zone, description) VALUES (?, ?)",
        sorted(ZONE_DESCRIPTIONS.items()),
    )
    connection.commit()


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


def download_csv(url: str, timeout: float = DOWNLOAD_TIMEOUT_SECONDS) -> str | None:
    """Fetch a public CSV over plain HTTP(S). Returns None on any failure."""
    if not url.lower().startswith(("http://", "https://")):
        print(f"  ! refusing non-http url: {url}", file=sys.stderr)
        return None
    request = urllib.request.Request(url, headers={"User-Agent": "construction-ingest/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - scheme checked above
            if response.status != 200:
                print(f"  ! HTTP {response.status} from {url}", file=sys.stderr)
                return None
            return response.read().decode("utf-8-sig", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        print(f"  ! download failed ({type(error).__name__}): {url}", file=sys.stderr)
        return None


def _header_index(headers: list[str], *candidates: str, fuzzy: bool = True) -> int | None:
    """Find a column by exact normalised name, then (optionally) by substring.

    ``fuzzy`` must be disabled for the climate-zone column: open postcode data
    routinely carries unrelated ``*zone`` columns (electricity ``chargezone``,
    delivery zones) that a substring match would silently pick up.
    """
    normalised = [re.sub(r"[^a-z0-9]", "", h.casefold()) for h in headers]
    for candidate in candidates:
        key = re.sub(r"[^a-z0-9]", "", candidate.casefold())
        if key in normalised:
            return normalised.index(key)
    if not fuzzy:
        return None
    for candidate in candidates:
        key = re.sub(r"[^a-z0-9]", "", candidate.casefold())
        for index, header in enumerate(normalised):
            if key and key in header:
                return index
    return None


def _validate_zone_column(rows: list[list[str]], index: int, sample: int = 400) -> bool:
    """Reject a candidate zone column whose values are not plausibly zones 1-8.

    Guards against a same-named column holding something else entirely (postal
    zones, price zones), which would otherwise be written as authoritative data.
    """
    values = [row[index].strip() for row in rows[:sample] if index < len(row) and row[index].strip()]
    if not values:
        return False
    parsed = sum(1 for value in values if coerce_zone(value) is not None)
    return parsed / len(values) >= 0.9


def parse_postcode_csv(text: str, source_label: str) -> list[PostcodeZone]:
    """Parse an open-data postcode CSV into ``PostcodeZone`` rows.

    Column names vary between sources, so headers are matched loosely. Rows
    carrying an explicit climate zone are ``authoritative``; rows that only
    supply postcode/suburb/state fall back to the bundled range seed.
    """
    reader = csv.reader(io.StringIO(text))
    try:
        headers = next(reader)
    except StopIteration:
        return []

    postcode_index = _header_index(headers, "postcode", "post code", "postal code", "poa")
    if postcode_index is None:
        print(f"  ! no postcode column in {source_label}", file=sys.stderr)
        return []
    suburb_index = _header_index(headers, "locality", "suburb", "place name", "name")
    state_index = _header_index(headers, "state", "state code", "st")
    zone_index = _header_index(
        headers, "climate zone", "climatezone", "abcb climate zone", "ncc climate zone", "zone", fuzzy=False
    )

    records = [row for row in reader if row]
    if zone_index is not None and not _validate_zone_column(records, zone_index):
        print(
            f"  ! ignoring column '{headers[zone_index]}' in {source_label}: "
            "values are not ABCB climate zones 1-8",
            file=sys.stderr,
        )
        zone_index = None

    rows: dict[tuple[str, str, str], PostcodeZone] = {}
    for record in records:
        def cell(index: int | None) -> str:
            if index is None or index >= len(record):
                return ""
            return record[index].strip()

        postcode = normalise_postcode(cell(postcode_index))
        if postcode is None:
            continue
        suburb = cell(suburb_index).title()
        state = cell(state_index).upper()
        if state and state not in STATES:
            state = state[:3] if state[:3] in STATES else ""

        zone = coerce_zone(cell(zone_index)) if zone_index is not None else None
        if zone is not None:
            confidence, source = "authoritative", source_label
        else:
            zone, seed_state, label = zone_for_postcode(postcode, suburb, state)
            if zone is None:
                continue
            state = state or seed_state
            confidence = "range_seed"
            source = f"{source_label} + range_seed ({label})" if label else source_label

        key = (postcode, suburb, state)
        candidate = PostcodeZone(
            postcode=postcode,
            suburb=suburb,
            state=state,
            climate_zone=zone,
            ncc_volume=DEFAULT_NCC_VOLUME,
            source=source,
            confidence=confidence,
        )
        existing = rows.get(key)
        # An authoritative row always wins over a seeded one for the same key.
        if existing is None or (existing.confidence != "authoritative" and confidence == "authoritative"):
            rows[key] = candidate
    return list(rows.values())


def build_range_seed_rows() -> list[PostcodeZone]:
    """Expand the bundled ranges into one row per 4-digit postcode."""
    rows: list[PostcodeZone] = []
    seen: set[str] = set()
    for postcode, (state, label) in ALPINE_POSTCODES.items():
        seen.add(postcode)
        rows.append(
            PostcodeZone(
                postcode=postcode,
                suburb="",
                state=state,
                climate_zone=8,
                ncc_volume=DEFAULT_NCC_VOLUME,
                source=f"range_seed (Alpine postcode - {label})",
                confidence="range_seed",
            )
        )
    for low, high, state, zone, label in POSTCODE_RANGE_SEED:
        for number in range(low, high + 1):
            postcode = f"{number:04d}"
            if postcode in seen:
                continue
            seen.add(postcode)
            rows.append(
                PostcodeZone(
                    postcode=postcode,
                    suburb="",
                    state=state,
                    climate_zone=zone,
                    ncc_volume=DEFAULT_NCC_VOLUME,
                    source=f"range_seed ({label})",
                    confidence="range_seed",
                )
            )
    return rows


def insert_rows(connection: sqlite3.Connection, rows: list[PostcodeZone]) -> int:
    """Insert rows, letting authoritative data replace seeded data."""
    if not rows:
        return 0
    connection.executemany(
        """
        INSERT INTO postcode_zones
            (postcode, suburb, state, climate_zone, ncc_volume, source, confidence)
        VALUES (:postcode, :suburb, :state, :climate_zone, :ncc_volume, :source, :confidence)
        ON CONFLICT (postcode, suburb, state) DO UPDATE SET
            climate_zone = excluded.climate_zone,
            ncc_volume   = excluded.ncc_volume,
            source       = excluded.source,
            confidence   = excluded.confidence
        WHERE excluded.confidence = 'authoritative'
        """,
        [row.as_dict() for row in rows],
    )
    connection.commit()
    return len(rows)


def set_metadata(connection: sqlite3.Connection, **values: str) -> None:
    connection.executemany(
        "INSERT OR REPLACE INTO build_metadata (key, value) VALUES (?, ?)",
        [(key, str(value)) for key, value in values.items()],
    )
    connection.commit()


# ---------------------------------------------------------------------------
# Query API
# ---------------------------------------------------------------------------


def lookup_postcode(
    connection: sqlite3.Connection,
    postcode: str | int,
    suburb: str | None = None,
) -> dict | None:
    """Look up one postcode, preferring authoritative and suburb-matched rows."""
    code = normalise_postcode(postcode)
    if code is None:
        return None
    rows = connection.execute(
        """
        SELECT postcode, suburb, state, climate_zone, ncc_volume, source, confidence
        FROM postcode_zones WHERE postcode = ?
        ORDER BY CASE confidence WHEN 'authoritative' THEN 0 ELSE 1 END,
                 CASE WHEN suburb = '' THEN 1 ELSE 0 END,
                 suburb
        """,
        (code,),
    ).fetchall()
    if not rows:
        return None

    chosen = rows[0]
    if suburb:
        key = suburb.casefold().strip()
        for row in rows:
            if row["suburb"] and row["suburb"].casefold().strip() == key:
                chosen = row
                break

    zones = sorted({row["climate_zone"] for row in rows})
    result = dict(chosen)
    result["zone_description"] = ZONE_DESCRIPTIONS.get(chosen["climate_zone"], "")
    result["localities_in_postcode"] = len(rows)
    result["zones_in_postcode"] = zones
    result["requires_confirmation"] = chosen["confidence"] != "authoritative" or len(zones) > 1
    result["confirmation_note"] = (
        "Climate-zone boundaries do not follow postcode boundaries. Confirm the "
        "project address on the ABCB Climate Map (https://ncc.abcb.gov.au/abcb-climate-map) "
        "before relying on this zone."
    )
    return result


def export_json(connection: sqlite3.Connection, path: Path | str = DEFAULT_JSON_PATH) -> Path:
    """Write a compact ``postcode -> zone`` map for instant offline lookup."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, dict] = {}
    for row in connection.execute(
        """
        SELECT postcode, state, climate_zone, confidence, COUNT(*) AS localities
        FROM postcode_zones
        GROUP BY postcode, state, climate_zone, confidence
        ORDER BY postcode,
                 CASE confidence WHEN 'authoritative' THEN 0 ELSE 1 END,
                 localities DESC
        """
    ):
        entry = mapping.setdefault(
            row["postcode"],
            {
                "state": row["state"],
                "climate_zone": row["climate_zone"],
                "confidence": row["confidence"],
                "zones": [],
                "ncc_volume": DEFAULT_NCC_VOLUME,
            },
        )
        if row["climate_zone"] not in entry["zones"]:
            entry["zones"].append(row["climate_zone"])
    for entry in mapping.values():
        entry["zones"].sort()
        entry["requires_confirmation"] = entry["confidence"] != "authoritative" or len(entry["zones"]) > 1
    output.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")
    return output


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def build_database(
    db_path: Path | str = DEFAULT_DB_PATH,
    csv_paths: list[Path] | None = None,
    urls: list[str] | None = None,
    offline: bool = False,
) -> dict:
    """Create the database, seed it, then overlay any authoritative sources."""
    connection = connect(db_path)
    create_schema(connection)

    seed_rows = build_range_seed_rows()
    insert_rows(connection, seed_rows)
    print(f"  seeded {len(seed_rows)} postcodes from bundled ranges")

    authoritative = 0
    for csv_path in csv_paths or []:
        path = Path(csv_path)
        if not path.is_file():
            print(f"  ! csv not found: {path}", file=sys.stderr)
            continue
        rows = parse_postcode_csv(path.read_text(encoding="utf-8-sig", errors="replace"), path.name)
        insert_rows(connection, rows)
        authoritative += sum(1 for row in rows if row.confidence == "authoritative")
        print(f"  loaded {len(rows)} rows from {path.name}")

    if not offline:
        for url in urls if urls is not None else PUBLIC_SOURCES:
            text = download_csv(url)
            if text is None:
                continue
            rows = parse_postcode_csv(text, url)
            insert_rows(connection, rows)
            authoritative += sum(1 for row in rows if row.confidence == "authoritative")
            print(f"  loaded {len(rows)} rows from {url}")

    total = connection.execute("SELECT COUNT(*) FROM postcode_zones").fetchone()[0]
    distinct = connection.execute("SELECT COUNT(DISTINCT postcode) FROM postcode_zones").fetchone()[0]
    set_metadata(
        connection,
        ncc_edition="NCC 2022",
        ncc_volume_note=NCC_VOLUME_NOTE,
        row_count=total,
        distinct_postcodes=distinct,
        authoritative_rows=authoritative,
    )
    connection.close()
    return {"rows": total, "distinct_postcodes": distinct, "authoritative_rows": authoritative}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite output path")
    parser.add_argument("--csv", action="append", default=[], help="local postcode/climate-zone CSV (repeatable)")
    parser.add_argument("--url", action="append", default=None, help="public CSV url (repeatable)")
    parser.add_argument("--offline", action="store_true", help="skip all downloads")
    parser.add_argument("--export-json", nargs="?", const=str(DEFAULT_JSON_PATH), help="also write a JSON lookup map")
    parser.add_argument("--lookup", help="after building, print the record for this postcode")
    args = parser.parse_args(argv)

    print(f"Building climate-zone database at {args.db}")
    stats = build_database(
        db_path=args.db,
        csv_paths=[Path(p) for p in args.csv],
        urls=args.url,
        offline=args.offline,
    )
    print(f"  {stats['rows']} rows / {stats['distinct_postcodes']} distinct postcodes "
          f"({stats['authoritative_rows']} authoritative)")

    connection = connect(args.db)
    if args.export_json:
        path = export_json(connection, args.export_json)
        print(f"  exported JSON lookup to {path}")
    if args.lookup:
        record = lookup_postcode(connection, args.lookup)
        print(json.dumps(record, indent=2) if record else f"  no record for {args.lookup}")
    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
