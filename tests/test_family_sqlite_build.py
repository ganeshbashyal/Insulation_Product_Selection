import json
import sqlite3
from pathlib import Path

import scripts.build_family_sqlite as builder


def test_family_sqlite_build_includes_variants_and_installation(tmp_path):
    knowledge = tmp_path / "knowledge"
    manufacturer = knowledge / "demo_mfg"
    (manufacturer / "research").mkdir(parents=True)

    families = {
        "schema_version": "2.0",
        "families": [
            {
                "family_id": "DEMO_MFG_SAMPLE_FAMILY",
                "manufacturer": "Demo Mfg",
                "name": "Sample Family",
                "category": "Bulk insulation",
                "primary_function": "Thermal performance",
                "applications": ["ceiling"],
                "keywords": ["ceiling insulation"],
                "confidence": "manufacturer_supported",
                "knowledge_file": "sample-family.md",
                "source_url": "https://example.com/sample-family",
            }
        ],
    }
    (manufacturer / "families.json").write_text(json.dumps(families), encoding="utf-8")

    research = {
        "family_id": "DEMO_MFG_SAMPLE_FAMILY",
        "family_name": "Sample Family",
        "status": "ok",
        "spec": {
            "range_headers": ["R-value", "Thickness (mm)", "Width (mm)", "Product code"],
            "range": [
                {"c0": "R2.5", "c1": "90", "c2": "430", "c3": "A123"},
                {"c0": "R3.0", "c1": "120", "c2": "430", "c3": "A124"},
            ],
            "install": ["Friction fit between joists", "Keep service clearance as per datasheet"],
            "clearances": ["Maintain 25 mm clearance around downlights"],
            "limitations": ["Do not compress during installation"],
        },
    }
    research_path = manufacturer / "research" / "sample_family.json"
    research_path.write_text(json.dumps(research), encoding="utf-8")

    db_path = tmp_path / "family_catalogue.sqlite3"
    builder.build_database(root=tmp_path, db_path=db_path)

    with sqlite3.connect(db_path) as connection:
        family = connection.execute("SELECT family_id, manufacturer FROM families WHERE family_id = ?", ("DEMO_MFG_SAMPLE_FAMILY",)).fetchone()
        assert family == ("DEMO_MFG_SAMPLE_FAMILY", "Demo Mfg")

        variant = connection.execute("SELECT family_id, r_value, thickness_mm, width_mm, product_code FROM family_variants WHERE family_id = ? ORDER BY rowid LIMIT 1", ("DEMO_MFG_SAMPLE_FAMILY",)).fetchone()
        assert variant[0] == "DEMO_MFG_SAMPLE_FAMILY"
        assert variant[1] == "R2.5"
        assert variant[2] == 90
        assert variant[3] == 430
        assert variant[4] == "A123"

        install_step = connection.execute("SELECT family_id, text FROM family_installation WHERE family_id = ? ORDER BY rowid LIMIT 1", ("DEMO_MFG_SAMPLE_FAMILY",)).fetchone()
        assert install_step[0] == "DEMO_MFG_SAMPLE_FAMILY"
        assert "Friction fit" in install_step[1]
