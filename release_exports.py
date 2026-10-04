"""Offline export adapters for a single explicitly activated serving release."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

from knowledge_release import ReleaseLibrary, visible_family_ids
from research_store import canonical


def cards(data: dict, site_id: str = "default") -> list[dict]:
    body = data["payload"]
    allowed = visible_family_ids(data, site_id)
    result = []
    for family in body["families"]:
        if family["family_id"] not in allowed:
            continue
        claims = body["evidence"][family["family_id"]]
        lines = [f"{family['name']} - {family['manufacturer']}",
                 "Identity for enquiry recognition only; suitability requires human review."]
        for claim in claims:
            lines.append(f"{claim['metric_type']}: {claim['value']} {claim['unit']}; "
                         f"variant {claim['variant']}; scope {claim['scope']}; "
                         f"test {claim['test_standard']}; context {claim['test_context']}; "
                         f"source {claim['source_url']}; {claim['source_locator']}")
        if not claims:
            lines.append("No reviewed technical claims; ask the team to check the source.")
        row = {"release_id": data["release_id"], "family_id": family["family_id"],
               "name": family["name"], "manufacturer": family["manufacturer"],
               "reviewed_claims": claims, "text": "\n".join(lines),
               "automatic_selection": False}
        row["card_hash"] = hashlib.sha256(canonical(row).encode()).hexdigest()
        result.append(row)
    return result


def export(library: ReleaseLibrary, destination: Path, site_id: str = "default") -> dict:
    data = library.active()
    if destination.exists():
        raise ValueError("Export requires a new named directory, not an overwrite")
    destination.mkdir(parents=True)
    rows = cards(data, site_id)
    allowed = {row["family_id"] for row in rows}
    catalogue = [row for row in data["payload"]["catalogue"] if row["family_id"] in allowed]
    (destination / "retrieval_cards.jsonl").write_text(
        "".join(canonical(row) + "\n" for row in rows), encoding="utf-8")
    lines = ["REVIEWED FAMILY KNOWLEDGE - ENQUIRY HANDOFF",
             f"Release: {data['release_id']}",
             "Give reviewed product facts or ask for missing source information.",
             "Do not recommend/select products, infer quantities, approve installation or compliance.",
             "Product/component tests are not installed system performance.",
             "Gather relevant project context and consent, then arrange human review.", ""]
    lines.extend(row["text"] + "\n" for row in rows)
    (destination / "voice_knowledge.txt").write_text("\n".join(lines), encoding="utf-8")
    with sqlite3.connect(destination / "knowledge.sqlite3") as connection:
        connection.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE release (release_id TEXT PRIMARY KEY);
            CREATE TABLE families (family_id TEXT PRIMARY KEY, name TEXT NOT NULL, manufacturer TEXT NOT NULL);
            CREATE TABLE claims (family_id TEXT NOT NULL REFERENCES families(family_id),
                evidence_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(family_id,evidence_id));
            CREATE TABLE catalogue (sku_record_id TEXT PRIMARY KEY, family_id TEXT NOT NULL
                REFERENCES families(family_id), payload TEXT NOT NULL, eligibility TEXT NOT NULL);
        """)
        connection.execute("INSERT INTO release VALUES (?)", (data["release_id"],))
        for row in rows:
            connection.execute("INSERT INTO families VALUES (?,?,?)",
                               (row["family_id"], row["name"], row["manufacturer"]))
            for claim in row["reviewed_claims"]:
                connection.execute("INSERT INTO claims VALUES (?,?,?)",
                                   (row["family_id"], claim["evidence_id"], canonical(claim)))
        for row in catalogue:
            eligibility = data["payload"]["eligibility"].get(row["sku_record_id"], {"eligible": False})
            connection.execute("INSERT INTO catalogue VALUES (?,?,?,?)",
                               (row["sku_record_id"], row["family_id"], canonical(row), canonical(eligibility)))
    if library.active_id() != data["release_id"]:
        raise ValueError("Release changed during export; partial directory has no valid manifest")
    manifest = {"release_id": data["release_id"], "site_id": site_id, "family_count": len(rows),
                "sku_count": len(catalogue), "automatic_selection": False,
                "files": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sorted(destination.iterdir())},
                "boundary": "Derived reviewed facts only. Re-export after withdrawal; do not deploy legacy authoring cards/databases."}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
