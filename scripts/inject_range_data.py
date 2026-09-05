"""Inject granular size/dimension/packaging data into family research specs.

One-off loader for a hand-supplied set of detailed variant/pack tables covering
10 Thermotec and Trade Select families. Each family's table becomes `range`
rows in knowledge/<mfg>/research/<slug>.json so the literature generator
renders the full size/pack breakdown. Existing research data is preserved; the
`range` field is replaced and a `range_source` note is added.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# family_id -> (manufacturer_dir, family_name, column headers, rows)
DATA = {
    "THERMOTEC_E_FLEX_HT": ("thermotec", "E-Flex HT Solar Pipe Insulation",
        ["Wall / R", "Pipe ID", "Fits Copper", "Imperial OD", "Carton (lineal m)", "Pcs/carton"], [
        ["13 mm (R0.38)", "10 mm", "DN10", '3/8"', "160 m", "80"],
        ["13 mm (R0.38)", "13 mm", "DN15", '1/2"', "136 m", "68"],
        ["13 mm (R0.38)", "19 mm", "DN20", '3/4"', "96 m", "48"],
        ["13 mm (R0.38)", "22 mm", "-", '7/8"', "84 m", "42"],
        ["13 mm (R0.38)", "25 mm", "DN25", '1"', "70 m", "35"],
        ["13 mm (R0.38)", "28 mm", "-", '1-1/8"', "60 m", "30"],
        ["13 mm (R0.38)", "35 mm", "DN32", '1-3/8"', "44 m", "22"],
        ["13 mm (R0.38)", "42 mm", "DN40", '1-5/8"', "36 m", "18"],
        ["13 mm (R0.38)", "54 mm", "DN50", '2-1/8"', "24 m", "12"],
        ["19 mm (R0.60)", "13 mm", "DN15", '1/2"', "72 m", "36"],
        ["19 mm (R0.60)", "19 mm", "DN20", '3/4"', "56 m", "28"],
        ["19 mm (R0.60)", "25 mm", "DN25", '1"', "48 m", "24"],
        ["19 mm (R0.60)", "35 mm", "DN32", '1-3/8"', "32 m", "16"],
        ["25 mm (R0.85)", "19 mm", "DN20", '3/4"', "36 m", "18"],
        ["25 mm (R0.85)", "25 mm", "DN25", '1"', "30 m", "15"],
    ]),
    "THERMOTEC_ROCKWOOL_PIPE": ("thermotec", "Rockwool Pipe Insulation",
        ["Nominal Bore", "Pipe OD", "25 mm wall (qty)", "38 mm wall (qty)", "50 mm wall (qty)"], [
        ["15 NB", "21.3 mm", "25 m (25 pcs)", "16 m (16 pcs)", "9 m (9 pcs)"],
        ["20 NB", "26.9 mm", "20 m (20 pcs)", "12 m (12 pcs)", "9 m (9 pcs)"],
        ["25 NB", "33.7 mm", "16 m (16 pcs)", "9 m (9 pcs)", "6 m (6 pcs)"],
        ["32 NB", "42.4 mm", "12 m (12 pcs)", "9 m (9 pcs)", "6 m (6 pcs)"],
        ["40 NB", "48.3 mm", "9 m (9 pcs)", "6 m (6 pcs)", "4 m (4 pcs)"],
        ["50 NB", "60.3 mm", "9 m (9 pcs)", "4 m (4 pcs)", "4 m (4 pcs)"],
        ["65 NB", "76.1 mm", "6 m (6 pcs)", "4 m (4 pcs)", "2 m (2 pcs)"],
        ["80 NB", "88.9 mm", "4 m (4 pcs)", "2 m (2 pcs)", "2 m (2 pcs)"],
        ["100 NB", "114.3 mm", "4 m (4 pcs)", "2 m (2 pcs)", "2 m (2 pcs)"],
        ["125 NB", "139.7 mm", "2 m (2 pcs)", "1 m (1 pc)", "1 m (1 pc)"],
        ["150 NB", "168.3 mm", "2 m (2 pcs)", "1 m (1 pc)", "1 m (1 pc)"],
        ["200 NB", "219.1 mm", "1 m (1 pc)", "1 m (1 pc)", "1 m (1 pc)"],
    ]),
    "THERMOTEC_E_THERM": ("thermotec", "E-Therm Reflective Roof and Wall Insulation",
        ["Grade", "Core thickness", "Roll width (net/gross)", "Roll length", "Coverage/roll", "Roll dia", "Weight", "Pallet"], [
        ["E-Therm 50", "5.0 mm", "1350/1500 mm", "22.25 m", "30.0 m2", "420 mm", "10.5 kg", "16 rolls"],
        ["E-Therm 65", "6.5/7.0 mm", "1350/1500 mm", "22.25 m", "30.0 m2", "460 mm", "12.8 kg", "12 rolls"],
        ["E-Therm 80", "8.0/8.5 mm", "1350/1500 mm", "22.25 m", "30.0 m2", "510 mm", "14.2 kg", "9 rolls"],
        ["E-Therm Commercial", "6.5 mm", "1350/1500 mm", "40.00 m", "54.0 m2", "620 mm", "23.0 kg", "6 rolls"],
    ]),
    "THERMOTEC_MAXTAPE_FR": ("thermotec", "MaxTape FR Insulating Foam Tape",
        ["Variant", "Thickness", "Width", "Length", "Area/roll", "Box qty", "Master carton"], [
        ["MaxTape FR 50", "3.0 mm", "50 mm", "9.1 m", "0.455 m2", "10 rolls", "91.0 lineal m"],
        ["MaxTape FR 98", "3.0 mm", "98 mm", "9.1 m", "0.892 m2", "5 rolls", "45.5 lineal m"],
        ["MaxTape FR Heavy", "6.0 mm", "50 mm", "7.5 m", "0.375 m2", "10 rolls", "75.0 lineal m"],
    ]),
    "THERMOTEC_MAXFLEX_PIPE": ("thermotec", "Maxflex Coil Pipe Insulation (identity unverified)",
        ["Wall", "Pipe IDs", "Pipe types", "Carton (lineal m)"], [
        ["9 mm", "6/10/13/16/19 mm", "AC copper / PEX", "160-200 m (80-100 pcs)"],
        ["9 mm", "22/25/28/35 mm", "Domestic hot & cold", "80-120 m (40-60 pcs)"],
        ["13 mm", "10/13/16/19/22 mm", "Refrigeration liquid/suction", "96-140 m (48-70 pcs)"],
        ["13 mm", "25/32/38/50 mm", "Chilled/hot water mains", "40-70 m (20-35 pcs)"],
        ["19 mm", "13/19/25/32 mm", "VRV/VRF suction", "36-64 m (18-32 pcs)"],
        ["19 mm", "38/50/65/75/100 mm", "Commercial HVAC chilled water", "12-28 m (6-14 pcs)"],
        ["25 mm", "19/25/32/38/50 mm", "Heavy condensation control", "16-32 m (8-16 pcs)"],
    ]),
    "TRADE_SELECT_ALUMINIUM_GLASS_FOIL_TAPE": ("trade select", "Trade Select Aluminium Glass Foil Tape",
        ["Width", "Length", "Area/roll", "Thickness", "Box qty", "Pallet"], [
        ["48 mm", "45 m", "2.16 m2", "130 microns", "24 rolls", "1152 rolls"],
        ["72 mm", "45 m", "3.24 m2", "130 microns", "16 rolls", "768 rolls"],
        ["96/100 mm", "45 m", "4.50 m2", "130 microns", "12 rolls", "576 rolls"],
        ["72 mm Heavy Duty", "50 m", "3.60 m2", "155 microns", "16 rolls", "768 rolls"],
    ]),
    "TRADE_SELECT_BALLISTIC_POINT_INSULATION_FASTENE": ("trade select", "Trade Select Ballistic Point Insulation Fastene",
        ["Code", "Pin length", "Washer dia", "Shank dia", "Board thickness", "Box qty"], [
        ["GTIF-30", "30 mm", "60 mm", "3.7 mm", "25-30 mm", "250 pcs"],
        ["GTIF-50", "50 mm", "60 mm", "3.7 mm", "40-50 mm", "250 pcs"],
        ["GTIF-60", "60 mm", "60 mm", "3.7 mm", "50-60 mm", "250 pcs"],
        ["GTIF-75", "75 mm", "60 mm", "3.7 mm", "65-75 mm", "200 pcs"],
        ["GTIF-100", "100 mm", "60 mm", "3.7 mm", "80-100 mm", "150 pcs"],
        ["GTIF-125", "125 mm", "60 mm", "3.7 mm", "110-125 mm", "100 pcs"],
    ]),
    "TRADE_SELECT_EASYSEAL_INSULATION_FLASHING_TAPE": ("trade select", "Trade Select EasySeal Insulation Flashing Tape",
        ["Width", "Length", "Area/roll", "Thickness", "Carton qty", "Application"], [
        ["50 mm", "20 m", "1.0 m2", "1.0 mm", "12 rolls", "Membrane overlaps & vertical joins"],
        ["75 mm", "20 m", "1.5 m2", "1.0 mm", "8 rolls", "Window jambs & narrow flashing"],
        ["100 mm", "20 m", "2.0 m2", "1.0 mm", "6 rolls", "Standard window reveals & duct collars"],
        ["150 mm", "20 m", "3.0 m2", "1.0 mm", "4 rolls", "Full window sill pan flashing"],
        ["200 mm", "20 m", "4.0 m2", "1.0 mm", "2 rolls", "Commercial deep window reveals"],
        ["300 mm", "20 m", "6.0 m2", "1.0 mm", "2 rolls", "Parapet caps & slab-edge junctions"],
    ]),
    "TRADE_SELECT_NC_THERMAL_BREAK_STRIPS": ("trade select", "Trade Select NC Thermal Break Strips",
        ["Thickness", "Width", "Length/strip", "Pack", "Pack lineal m", "Pallet"], [
        ["10 mm (R0.24)", "42 mm", "1200 mm", "50 strips", "60.0 lm", "40 packs (2400 lm)"],
        ["10 mm (R0.24)", "45 mm", "1200 mm", "50 strips", "60.0 lm", "40 packs (2400 lm)"],
        ["10 mm (R0.24)", "50 mm", "1200 mm", "50 strips", "60.0 lm", "36 packs (2160 lm)"],
        ["10 mm (R0.24)", "75 mm", "1200 mm", "30 strips", "36.0 lm", "32 packs (1152 lm)"],
    ]),
    "TRADE_SELECT_NC_THERMAL_BREAK_STRIPS_ADHESIVE_BACKED": ("trade select", "Trade Select NC Thermal Break Strips Adhesive backed",
        ["Thickness", "Width", "Length/strip", "Adhesive", "Pack lineal m", "Pallet"], [
        ["10 mm (R0.24)", "42 mm", "1200 mm", "Full-width high-tack PSA", "60.0 lm (50 strips)", "40 packs (2400 lm)"],
        ["10 mm (R0.24)", "45 mm", "1200 mm", "Full-width high-tack PSA", "60.0 lm (50 strips)", "40 packs (2400 lm)"],
        ["10 mm (R0.24)", "50 mm", "1200 mm", "Full-width high-tack PSA", "60.0 lm (50 strips)", "36 packs (2160 lm)"],
        ["10 mm (R0.24)", "75 mm", "1200 mm", "Full-width high-tack PSA", "36.0 lm (30 strips)", "32 packs (1152 lm)"],
    ]),
}


def slugify(name: str) -> str:
    import re
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()[:60]


def main() -> None:
    updated = created = 0
    for family_id, (mdir, family_name, headers, rows) in DATA.items():
        slug = slugify(family_name)
        path = ROOT / "knowledge" / mdir / "research" / f"{slug}.json"
        range_rows = [dict(zip(["c%d" % i for i in range(len(headers))], row)) for row in rows]
        # store headers alongside so the generator can render them
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            updated += 1
        else:
            data = {
                "family_id": family_id, "family_name": family_name,
                "datasheet_pdf_url": "", "sds_url": "", "status": "ok",
                "researched_at": time.strftime("%Y-%m-%d"),
                "spec": {}, "retrieval": {}, "source_excerpt": None,
                "engine": "manual_range_injection",
            }
            created += 1
        spec = data.setdefault("spec", {})
        spec["range"] = range_rows
        spec["range_headers"] = headers
        data["range_source"] = "manufacturer size/packaging breakdown (hand-supplied 2026-09-06)"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  {'updated' if path.exists() else 'created'}  {family_id}")
    print(f"\nupdated: {updated}, created: {created}")


if __name__ == "__main__":
    main()
