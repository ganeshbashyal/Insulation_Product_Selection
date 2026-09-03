---
family_id: FLETCHER_PINK_BATTS_FLOOR
manufacturer: Fletcher Insulation
canonical_name: Pink Batts Floor Insulation
category: Glasswool floor batt
validation_status: manufacturer_supported_current_sku_reconciliation_required
last_validated: 2026-09-04
recommendation_scope: family_only
official_datasheet_url: https://insulation.com.au/wp-content/uploads/2024/TDS-Pink-Batts-Floor-Rev2-15042024-2.pdf
---

# Pink Batts Floor Insulation

## Canonical description

FBS-1 glasswool batts intended for suitable suspended-floor systems to reduce heat flow and improve thermal comfort. They are bulk insulation between/under floor framing, not a resilient acoustic underlay. The complete installation needs retention, wind protection where applicable, moisture management and safe service clearances.

## Selection logic

Use Pink Batts Floor when underfloor thermal performance is the primary need and the framing permits secure, uncompressed installation. Use NuWave Underlay when impact noise beneath a compatible floor finish is the primary problem. Do not promise a floor-system acoustic rating from glasswool alone.

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Energy efficiency | 5 | High | Direct suspended-floor thermal role. |
| Acoustic comfort | 3 | Low | May assist an assembly; no standalone rating. |
| Sustainability | 4 | Medium | Glasswool environmental evidence applies only where product scope matches. |
| Installation practicality | 3 | Medium | Retention, crawl-space access and exposure are significant. |
| Compliance readiness | 3 | Medium | Confirm current code, R-value and installation scope. |
| BAL suitability | Gate | High | Underfloor exposure and complete construction need project review. |

## Mandatory inputs and safeguards

Capture floor type, joist spacing/depth, target material and Total R-value, clearance/access, subfloor ventilation, wind/water/pest exposure, retention method, services, climate zone and BAL/fire requirement. Never leave batts unsupported or exposed contrary to the installation guide. Reconcile every spreadsheet SKU to the current TDS before exact quoting.

## Approved bot language

> Pink Batts Floor is a thermal batt family for a compatible suspended floor. I can recommend the family, while the exact batt and retention/detailing need confirmation from the framing, exposure and current data sheet.

## Source

[Fletcher Pink Batts Floor TDS](https://insulation.com.au/wp-content/uploads/2024/TDS-Pink-Batts-Floor-Rev2-15042024-2.pdf)

```json
{"family_id":"FLETCHER_PINK_BATTS_FLOOR","recommendation_level":"family_only","best_for":["suspended floor thermal insulation"],"not_for":["impact-noise underlay"],"required_inputs":["floor_type","joist_spacing","cavity_depth","target_r","exposure","retention"],"human_gates":["current_sku","installation_method","moisture","total_r","BAL"]}
```
