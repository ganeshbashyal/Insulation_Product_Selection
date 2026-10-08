"""Read-only comparisons from explicitly owner-supplied local pricing snapshots."""
from __future__ import annotations

from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re


PRICE_DIR = Path("data/local/oracle_pricing")
PRICE_WORDS = re.compile(r"\b(price|pricing|cost|cheaper|expensive|competitor|compare\s+prices?)\b", re.I)


class OraclePricingError(ValueError):
    pass


def _norm(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _load(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OraclePricingError(f"Cannot read local pricing snapshot {path.name}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise OraclePricingError(f"{path.name}: expected pricing snapshot schema_version 1")
    if not isinstance(payload.get("source_name"), str) or not payload["source_name"].strip():
        raise OraclePricingError(f"{path.name}: source_name is required")
    currency = payload.get("currency")
    region = payload.get("region")
    effective_date = payload.get("effective_date")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        raise OraclePricingError(f"{path.name}: currency must be a three-letter uppercase code")
    if not isinstance(region, str) or not region.strip():
        raise OraclePricingError(f"{path.name}: region is required")
    try:
        date.fromisoformat(effective_date)
    except (TypeError, ValueError) as exc:
        raise OraclePricingError(f"{path.name}: effective_date must be YYYY-MM-DD") from exc
    rows = payload.get("prices")
    if not isinstance(rows, list):
        raise OraclePricingError(f"{path.name}: prices must be a list")
    normalized = []
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise OraclePricingError(f"{path.name}: price row {number} must be an object")
        required = ("competitor", "product_name", "comparison_key", "unit", "price")
        if any(not isinstance(row.get(key), str) or not row[key].strip() for key in required[:-1]):
            raise OraclePricingError(f"{path.name}: price row {number} needs competitor, product_name, comparison_key and unit")
        price = row.get("price")
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price < 0:
            raise OraclePricingError(f"{path.name}: price row {number} has invalid price")
        normalized.append({
            "competitor": row["competitor"].strip(),
            "product_name": row["product_name"].strip(),
            "comparison_key": _norm(row["comparison_key"]),
            "sku": row.get("sku") if isinstance(row.get("sku"), str) else "",
            "unit": row["unit"].strip(),
            "price": price,
            "currency": currency,
            "region": region.strip(),
            "effective_date": effective_date,
            "source_name": payload["source_name"].strip(),
        })
    return {"rows": normalized, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "path": path}


def analyze(root: Path, query: str) -> dict | None:
    """Return exact-key local comparisons only; return None when price intent is absent."""
    if not PRICE_WORDS.search(query):
        return None
    directory = root / PRICE_DIR
    if not directory.is_dir():
        return {"state": "no_local_price_data", "evidence": [{
            "kind": "pricing_gap", "status": "no local pricing snapshot",
            "text": "No owner-supplied local pricing snapshots are configured. No current price or competitor comparison is available.",
        }], "sources": []}
    snapshots = [_load(path) for path in sorted(directory.glob("*.json")) if path.is_file()]
    query_norm = _norm(query)
    query_terms = set(query_norm.split())
    selected = []
    for snapshot in snapshots:
        for row in snapshot["rows"]:
            keys = {_norm(row["product_name"]), _norm(row["comparison_key"]), _norm(row["sku"])}
            exact = any(key and (key in query_norm or query_norm in key) for key in keys)
            overlap = any(
                key and len(key.split()) >= 2
                and len(query_terms.intersection(key.split())) / len(key.split()) >= 0.75
                for key in keys
            )
            if exact or overlap:
                selected.append((snapshot, row, exact))
    if not selected:
        return {"state": "no_matching_local_price_data", "evidence": [{
            "kind": "pricing_gap", "status": "no exact local price match",
            "text": "No local pricing snapshot matches this product or comparison key; prices were not estimated.",
        }], "sources": []}
    selected.sort(key=lambda item: (not item[2], item[1]["comparison_key"], item[1]["currency"],
                                    item[1]["region"], item[1]["unit"], item[1]["competitor"]))
    evidence = []
    for snapshot, row, _ in selected[:30]:
        group = [other for _, other, _ in selected
                 if other["comparison_key"] == row["comparison_key"]
                 and other["currency"] == row["currency"] and other["region"] == row["region"]
                 and other["unit"] == row["unit"]]
        comparable_count = len({other["competitor"] for other in group})
        evidence.append({
            "kind": "local_pricing_snapshot", "status": "owner-supplied; not independently verified",
            "text": (f"{row['competitor']} / {row['product_name']} (SKU {row['sku'] or 'not supplied'}): "
                     f"{row['price']} {row['currency']} per {row['unit']}; region {row['region']}; "
                     f"effective {row['effective_date']}; source {row['source_name']}. "
                     f"Exact comparison key: {row['comparison_key']}; matching competitor count for "
                     f"currency/region/unit: {comparable_count}. No winner or suitability inference."),
            "source_file": snapshot["path"].relative_to(root).as_posix(),
            "source_sha256": snapshot["sha256"],
        })
    sources = [{
        "path": snapshot["path"].relative_to(root).as_posix(),
        "sha256": snapshot["sha256"],
        "status": "owner-supplied local pricing snapshot; not independently verified",
    } for snapshot in snapshots if any(row["source_file"] == snapshot["path"].relative_to(root).as_posix()
                                       for row in evidence)]
    return {"state": "local_snapshot_matches", "evidence": evidence, "sources": sources}


def template() -> dict:
    return {
        "schema_version": 1,
        "source_name": "Owner-provided source name",
        "currency": "AUD",
        "region": "AU-NSW",
        "effective_date": "YYYY-MM-DD",
        "prices": [{
            "competitor": "Supplier or competitor name",
            "product_name": "Exact product name",
            "comparison_key": "Owner-confirmed equivalent product/variant key",
            "sku": "Optional exact SKU",
            "unit": "each",
            "price": 0.0,
        }],
    }
