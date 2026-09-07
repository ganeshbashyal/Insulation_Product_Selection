# Australian Insulation Industry — Master Knowledge Index

*This is the entry point for any agent (human or AI) working on Australian insulation. All learnings are documented here for hand-off.*

> **Training a bot?** Start at [BOT_TRAINING_PACKAGE.md](BOT_TRAINING_PACKAGE.md) — the consolidated manifest with the fine-tuning dataset and RAG recipe.

---

## What's in this workspace

Three knowledge layers, each self-contained and cross-referenced:

### 1. Industry Knowledge Base (broad expertise)
[`AU_Insulation_Expert_Knowledge_Base.md`](AU_Insulation_Expert_Knowledge_Base.md)
- Regulatory framework (NCC 2022/2025)
- Thermal & acoustic principles
- Manufacturers & products (overview)
- Climate zones, installation, bushfire

### 2. Compliance Intelligence (ABCB handbooks + NCC)
[`compliance/`](compliance/README.md)
- [01_condensation_management.md](compliance/01_condensation_management.md) — vapour permeance, mould index, control layers
- [02_sound_transmission.md](compliance/02_sound_transmission.md) — Rw+Ctr, Ln,w, discontinuous construction
- [03_ncc_energy_efficiency.md](compliance/03_ncc_energy_efficiency.md) — 7-star, R-values, thermal bridging
- [04_industry_reports.md](compliance/04_industry_reports.md) — AIIC policy, state performance
- [05_standards_reference.md](compliance/05_standards_reference.md) — all standards, VCM classes, climate zones
- `raw/` — full extracted text of ABCB handbooks + NCC relevant pages

### 3. Product Intelligence (manufacturers + products + materials)
[`product_intelligence/`](product_intelligence/README.md)
- [01_manufacturers_suppliers.md](product_intelligence/01_manufacturers_suppliers.md) — 11+ manufacturers, ownership, brands, warranties
- [02_products_application.md](product_intelligence/02_products_application.md) — products by application + R-values
- [03_materials_applications.md](product_intelligence/03_materials_applications.md) — 10 materials, properties, selection matrix

### 4. Principles (thermal & acoustic deep dive)
[`principles/`](principles/README.md)
- [01_thermal_principles.md](principles/01_thermal_principles.md) — heat transfer, R/U-value, thermal bridging, thermal mass, solar
- [02_acoustic_principles.md](principles/02_acoustic_principles.md) — sound, mass law, mass-spring-mass, ratings, flanking, impact

### 5. Training Data (bot-training corpus)
[`training/`](training/README.md)
- [01_glossary.md](training/01_glossary.md) — 120+ terms
- [02_climate_zone_guide.md](training/02_climate_zone_guide.md) — per-zone strategy
- [03_installation_guide.md](training/03_installation_guide.md) — best practice + mistakes
- [04_bushfire.md](training/04_bushfire.md) — AS 3959 BAL
- [05_qa_pairs.md](training/05_qa_pairs.md) + [qa_pairs.json](training/qa_pairs.json) — 80 Q&A pairs (fine-tuning/RAG)

### 6. Customer Support (troubleshooting playbook)
[`customer_support/`](customer_support/README.md)
- [01_top_50_customer_problems.md](customer_support/01_top_50_customer_problems.md) — 50 problems with root cause + resolution
- [02_quick_triage.md](customer_support/02_quick_triage.md) — symptom → cause → solution reference

### 7. Tools (interactive compliance tool)
[`tools/`](tools/README.md)
- [compliance_tool.html](tools/compliance_tool.html) — interactive web tool (climate zone, NCC, BAL, sound)

---

## Hand-off notes for future agents

1. **Start here** — read this index, then the relevant layer for the task.
2. **Compliance questions** → `compliance/` (condensation, sound, energy, standards).
3. **Product/manufacturer questions** → `product_intelligence/`.
4. **Thermal/acoustic physics** → `principles/` (deep dive).
5. **Bot training data** → `training/` (glossary, guides, Q&A pairs).
6. **Customer problems** → `customer_support/` (50 problems + triage).
7. **Interactive tool** → `tools/compliance_tool.html` (climate zone, NCC, BAL, sound).
8. **General principles** → `AU_Insulation_Expert_Knowledge_Base.md`.
9. **Raw source text** → `compliance/raw/` (full handbook text + NCC extracts).
10. **Original PDFs** → session scratchpad `downloads/` (8 PDFs, if still available).

## Key facts (locked in, verified)

- **Vapour permeance (NCC 2025):** Class 3 (≥0.143 µg/N·s) zones 4–5; Class 4 (≥1.14 µg/N·s) zones 6–8; drained & ventilated cavity mandatory zones 6–8.
- **Sound:** Rw+Ctr ≥50 (SOU walls/floors), Rw ≥45 (Class 1 Type B), Ln,w ≤62 (impact), discontinuous = 20mm cavity + resilient ties.
- **Energy:** 7-star NatHERS; Total R-Value per AS/NZS 4859.2; slab edge mandatory zones 7–8.
- **Highest ceiling R-value:** Knauf Earthwool R8.0.
- **Thinnest board per R:** Kingspan Kooltherm (phenolic, λ 0.021 W/mK).
- **Non-irritant:** Polyester (Polymax, GreenStuf).
- **8 NCC climate zones:** 1 (Darwin) → 8 (Alpine).

## Data freshness

Compiled September 2026. NCC 2025 is current; state adoption of NCC 2022 7-star completed by May 2025 (WA last). Re-verify against ABCB website for the latest amendments before formal compliance advice.
