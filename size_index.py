"""Structured size/rating index over the SKU catalogue and research range tables.

Lets the bot answer "do you have R2.5 in a 430mm width?" style questions by
looking up which families actually carry a variant at that width, thickness or
R-value, instead of guessing. Built once at import from:
  - data/processed/product_catalogue_skus.csv  (product names + ratings)
  - knowledge/*/research/*.json                (granular range tables)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent

_DIM_RE = re.compile(r"(\d{3,4})\s*[xX×]\s*(\d{2,4})")
_THICK_RE = re.compile(r"\b(\d{2,3})\s*mm\b")
_RATING_RE = re.compile(r"R\s?(\d+(?:\.\d+)?)", re.I)


def _num(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_index() -> dict:
    """Return {family_id: {name, manufacturer, widths, thicknesses, rvalues}}."""
    index: dict[str, dict] = {}

    def entry(family_id: str, name: str, manufacturer: str) -> dict:
        return index.setdefault(family_id, {
            "family_id": family_id, "name": name, "manufacturer": manufacturer,
            "widths": set(), "thicknesses": set(), "rvalues": set(),
        })

    csv_path = ROOT / "data" / "processed" / "product_catalogue_skus.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path).fillna("")
        for _, row in df.iterrows():
            e = entry(row["family_id"], row["family_name"], row["manufacturer"])
            text = f"{row['product_name']} {row['our_sku']} {row['supplier_sku']}"
            for length, width in _DIM_RE.findall(text):
                w = _num(width)
                if w and 50 <= w <= 1500:  # plausible insulation width in mm
                    e["widths"].add(int(w))
            for token in _THICK_RE.findall(text):
                t = _num(token)
                if t and 5 <= t <= 300:
                    e["thicknesses"].add(int(t))
            for rating in _RATING_RE.findall(str(row["thermal_r_value"])):
                r = _num(rating)
                if r:
                    e["rvalues"].add(round(r, 2))

    for path in sorted(ROOT.glob("knowledge/*/research/*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        family_id = data.get("family_id")
        if not family_id:
            continue
        e = entry(family_id, data.get("family_name", ""), path.parent.parent.name.title())
        for row in (data.get("spec") or {}).get("range", []) or []:
            blob = " ".join(str(v) for v in row.values())
            for length, width in _DIM_RE.findall(blob):
                w = _num(width)
                if w and 50 <= w <= 1500:
                    e["widths"].add(int(w))
            for token in _THICK_RE.findall(blob):
                t = _num(token)
                if t and 5 <= t <= 300:
                    e["thicknesses"].add(int(t))
            for rating in _RATING_RE.findall(blob):
                r = _num(rating)
                if r:
                    e["rvalues"].add(round(r, 2))

    for e in index.values():
        e["widths"] = sorted(e["widths"])
        e["thicknesses"] = sorted(e["thicknesses"])
        e["rvalues"] = sorted(e["rvalues"])
    return index


INDEX = build_index()


def query(width: float | None = None, thickness: float | None = None, rvalue: float | None = None, element: str | None = None) -> list[dict]:
    """Families carrying a variant matching all supplied constraints."""
    matches = []
    for e in INDEX.values():
        if width is not None and not any(abs(w - width) <= 5 for w in e["widths"]):
            continue
        if thickness is not None and not any(abs(t - thickness) <= 2 for t in e["thicknesses"]):
            continue
        if rvalue is not None and not any(abs(r - rvalue) <= 0.15 for r in e["rvalues"]):
            continue
        matches.append(e)
    return matches
