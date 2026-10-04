"""Content-addressed local serving snapshots with explicit activation and withdrawals."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import uuid
from functools import lru_cache
from datetime import datetime
import math

from research_store import canonical

RELEASE_ID = re.compile(r"^[0-9a-f]{64}$")


def checked_claim(item: dict) -> None:
    fields = ("evidence_id", "verified_by", "verified_at", "source_locator", "source_url",
              "variant", "scope", "test_context", "test_standard", "metric_type")
    if not isinstance(item, dict) or any(not isinstance(item.get(key),str) or not item[key].strip() for key in fields):
        raise ValueError("Verified claim lacks mandatory review/citation provenance")
    if item.get("evidence_status") != "verified" or not item["source_url"].startswith("https://"):
        raise ValueError("Unverified or uncited technical claim")
    when = datetime.fromisoformat(item["verified_at"].replace("Z","+00:00"))
    if when.tzinfo is None or re.search(r"\b(?:pending|unknown)\b",item["source_locator"],re.I):
        raise ValueError("Incomplete verification timestamp or source locator")
    value=item.get("value")
    if isinstance(value,bool) or not isinstance(value,(str,int,float)) or (
            isinstance(value,(int,float)) and not math.isfinite(value)) or not isinstance(item.get("unit"),str):
        raise ValueError("Invalid verified metric value/unit")


def build(reader, visibility: dict | None = None) -> dict:
    idx = reader.index()
    if hasattr(idx, "root"):
        from jsonschema import Draft202012Validator, FormatChecker
        schema = json.loads((idx.root / "schemas" / "families.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator({"$ref":"#/$defs/family","$defs":schema["$defs"]},
                                        format_checker=FormatChecker())
        for family in idx.families.values():
            clean = {key:value for key,value in family.items() if key != "record_path"}
            errors = list(validator.iter_errors(clean))
            if errors:
                raise ValueError(f"Family schema invalid: {family['family_id']}: {errors[0].message}")
    evidence, publication = reader.evidence()
    if publication["state"] not in {"published", "baseline_only"}:
        raise ValueError("Active publication is held; resolve source/reviewer changes before releasing")
    claims = {}
    for key in idx.families:
        claims[key] = [item for item in evidence.get(key, []) if item.get("evidence_status") == "verified"]
        for item in claims[key]:
            checked_claim(item)
    body = {"schema_version": 1, "baseline": idx.baseline(),
            "publication_id": publication["publication_id"],
            "families": [{key:value for key,value in row.items() if key != "record_path"}
                         for row in idx.families.values()], "evidence": claims,
            "revoked": publication["revoked"],
            "catalogue": [{key: row.get(key,"") for key in (
                "sku_record_id","family_id","our_sku","supplier_sku","product_name",
                "manufacturer","source_sha256","validation_status","bot_content_status","active")}
                for row in idx.skus], "eligibility": publication["eligibility"],
            "gaps": [{"family_id": row["family_id"], "source_held": row["source_held"],
                      "sku_count": row["sku_count"]} for row in idx.browse(limit=len(idx.families))["families"]],
            "site_visibility": visibility if visibility is not None else {"*": sorted(idx.families)},
            "automatic_selection": False}
    return {"release_id": hashlib.sha256(canonical(body).encode()).hexdigest(), "payload": body}


def validate(data: dict) -> dict:
    if not isinstance(data, dict) or set(data) != {"release_id", "payload"}:
        raise ValueError("Invalid release envelope")
    body = data["payload"]
    if not RELEASE_ID.fullmatch(data["release_id"]) or hashlib.sha256(canonical(body).encode()).hexdigest() != data["release_id"]:
        raise ValueError("Release checksum mismatch")
    if body["schema_version"] != 1 or body["automatic_selection"] is not False:
        raise ValueError("Unsupported release or automatic selection")
    ids = [row["family_id"] for row in body["families"]]
    skus = [row["sku_record_id"] for row in body["catalogue"]]
    if len(ids) != len(set(ids)) or len(skus) != len(set(skus)):
        raise ValueError("Release has duplicate family/SKU identities")
    visibility = body.get("site_visibility", {"*": ids})
    if not isinstance(visibility, dict) or not visibility:
        raise ValueError("Explicit site visibility mapping required")
    for site, allowed in visibility.items():
        if not isinstance(site, str) or (site != "*" and not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", site)):
            raise ValueError("Invalid visibility site identity")
        if not isinstance(allowed, list) or any(not isinstance(key, str) or key not in ids for key in allowed) or len(set(allowed)) != len(allowed):
            raise ValueError("Visibility must reference unique canonical family IDs")
    for family in body["families"]:
        if any(not isinstance(family.get(key),str) or not family[key].strip()
               for key in ("family_id","name","manufacturer","confidence","category","primary_function")):
            raise ValueError("Family is missing required identity/description fields")
        if any(not isinstance(family.get(key),list) or not family[key]
               or any(not isinstance(value,str) for value in family[key])
               for key in ("applications","keywords","questions","human_gates")):
            raise ValueError("Family lacks required discovery lists")
        required_scores = {"acoustic_comfort", "energy_efficiency", "sustainability",
                           "installation_practicality", "compliance_readiness"}
        if not isinstance(family.get("scores"),dict) or set(family["scores"]) != required_scores or any(type(value) is not int or not 0<=value<=5 for value in family["scores"].values()):
            raise ValueError("Family has invalid internal discovery scores")
    if any(row["family_id"] not in ids for row in body["catalogue"]):
        raise ValueError("Release has unlinked SKU rows")
    if set(body["evidence"]) != set(ids):
        raise ValueError("Every family needs an explicit evidence list")
    if any(item.get("evidence_status") != "verified" for rows in body["evidence"].values() for item in rows):
        raise ValueError("Unreviewed evidence in serving release")
    for rows in body["evidence"].values():
        if len({item["evidence_id"] for item in rows}) != len(rows):
            raise ValueError("Duplicate reviewed evidence identity")
        for item in rows:
            checked_claim(item)
    if any(key not in skus or approval["family_id"] not in ids for key,approval in body["eligibility"].items()):
        raise ValueError("Eligibility references missing family/SKU")
    for key, approval in body["eligibility"].items():
        if type(approval["eligible"]) is not bool:
            raise ValueError("Eligibility must be an explicit boolean")
        if approval["eligible"]:
            row=next(row for row in body["catalogue"] if row["sku_record_id"]==key)
            if row["family_id"] != approval["family_id"] or not approval["evidence_ids"]:
                raise ValueError("Eligible SKU needs matching family and explicit evidence applicability")
            claims = {item["evidence_id"]: item for item in body["evidence"][approval["family_id"]]}
            if any(identifier not in claims or claims[identifier]["scope"] not in {"product","component"}
                   for identifier in approval["evidence_ids"]):
                raise ValueError("SKU eligibility references missing or inapplicable reviewed evidence")
    return data


class ReleaseLibrary:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()

    def save(self, data: dict) -> Path:
        validate(data)
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / (data["release_id"][:16] + ".json")
        content = canonical(data)
        legacy = self.directory / (data["release_id"] + ".json")
        if legacy.exists():
            if legacy.read_text(encoding="utf-8") != content:
                raise ValueError("Immutable legacy release was modified")
            return legacy
        if path.exists():
            if path.read_text(encoding="utf-8") != content:
                raise ValueError("Immutable release was modified")
            return path
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def read(self, identifier: str) -> dict:
        if not RELEASE_ID.fullmatch(identifier):
            raise ValueError("Invalid release ID")
        path = self.directory / (identifier[:16] + ".json")
        if not path.exists():
            path = self.directory / (identifier + ".json")
        data = validate(json.loads(path.read_text(encoding="utf-8")))
        if data["release_id"] != identifier:
            raise ValueError("Release filename prefix collision")
        return data

    def activate(self, identifier: str, confirm: str, expected: str | None) -> None:
        lock = self.directory / "activation.lock"
        with lock.open("x", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
        try:
            self._activate(identifier, confirm, expected)
        finally:
            lock.unlink()

    def _activate(self, identifier: str, confirm: str, expected: str | None) -> None:
        if confirm != identifier:
            raise ValueError("Exact release ID approval required")
        data = self.read(identifier)
        current = self.active_id()
        if current != expected:
            raise ValueError("Active release changed since preview")
        withdrawals = []
        pointer = self.directory / "active.json"
        if pointer.exists():
            withdrawals = json.loads(pointer.read_text(encoding="utf-8"))["withdrawals"]
        withdrawals = list({canonical(item): item for item in withdrawals + data["payload"]["revoked"]}.values())
        forbidden = {(item["family_id"], item["evidence_id"]) for item in withdrawals}
        if any((key, item["evidence_id"]) in forbidden for key, items in data["payload"]["evidence"].items() for item in items):
            raise ValueError("Activation/rollback would resurrect withdrawn evidence")
        temporary = self.directory / ("a-" + uuid.uuid4().hex[:12] + ".tmp")
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                handle.write(canonical({"release_id": identifier, "withdrawals": withdrawals}))
            os.replace(temporary, pointer)
        finally:
            temporary.unlink(missing_ok=True)

    def active_id(self) -> str | None:
        pointer = self.directory / "active.json"
        return json.loads(pointer.read_text(encoding="utf-8"))["release_id"] if pointer.exists() else None

    def active(self) -> dict:
        identifier = self.active_id()
        if identifier is None:
            raise ValueError("No explicitly activated serving release")
        return self.read(identifier)


@lru_cache(maxsize=8)
def _pinned_release(directory: str) -> dict:
    return ReleaseLibrary(Path(directory)).active()


def configured_release() -> dict | None:
    directory = os.getenv("AURORA_RELEASE_DIR")
    return _pinned_release(directory) if directory else None


def visible_family_ids(data: dict, site_id: str) -> set[str]:
    policy = data["payload"].get("site_visibility")
    if policy is None:
        return {row["family_id"] for row in data["payload"]["families"]}
    return set(policy.get(site_id, policy.get("*", [])))
