"""Guard: family source_urls must stay on official manufacturer domains.

Regression test for the 2026-09-05 audit that found 214 of 287 families
pointing at reseller/aggregator sites instead of manufacturer datasheets.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_datasheet_links import OFFICIAL_DOMAINS, UNVERIFIED_MANUFACTURERS, classify, domain_of, domain_matches


def all_families():
    for path in sorted((ROOT / "knowledge").glob("*/families.json")):
        for family in json.loads(path.read_text(encoding="utf-8"))["families"]:
            yield path.parent.name, family


def test_no_family_points_at_a_wrong_domain_for_verified_manufacturers():
    offenders = []
    for manufacturer, family in all_families():
        if manufacturer in UNVERIFIED_MANUFACTURERS:
            continue
        status = classify(manufacturer, (family.get("source_url") or "").strip())
        if status == "WRONG_DOMAIN":
            offenders.append(f"{manufacturer}: {family['family_id']} -> {family.get('source_url')}")
    assert offenders == [], "families with non-manufacturer datasheet links:\n" + "\n".join(offenders)


def test_repointed_families_are_flagged_tds_pending():
    flagged = 0
    for manufacturer, family in all_families():
        url = (family.get("source_url") or "").strip()
        official = OFFICIAL_DOMAINS.get(manufacturer) or []
        # site-root repoints are exactly the official root path, not deep links
        if official and domain_matches(domain_of(url), official):
            from urllib.parse import urlparse
            if urlparse(url).path.strip("/") in ("", "en", "group", "au", "en-AU/knauf-insulation"):
                flagged += 1
                assert family.get("source_url_status") == "manufacturer_site_root_tds_pending" or manufacturer in (
                    "fletcher", "stinger", "rockwool", "knauf",
                ), f"{family['family_id']} sits at a site root without the tds-pending flag"
    assert flagged > 0


def test_repointed_families_have_official_source_and_preserve_legacy_when_one_existed():
    flagged = 0
    for manufacturer, family in all_families():
        if family.get("source_url_status") != "manufacturer_site_root_tds_pending":
            continue
        flagged += 1
        official = OFFICIAL_DOMAINS.get(manufacturer) or []
        assert official and domain_matches(domain_of(family["source_url"]), official), (
            f"{family['family_id']} flagged tds-pending but source_url is not on the official domain"
        )
        if family.get("legacy_source_url"):
            assert not domain_matches(domain_of(family["legacy_source_url"]), official), (
                f"{family['family_id']} legacy_source_url was not actually wrong-domain"
            )
    assert flagged > 200, "expected the 2026-09-05 remediation to have flagged most families"
