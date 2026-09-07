# Bot Training Package — Manifest

*Consolidated specification for training/fine-tuning an Australian insulation expert bot. Last updated: September 2026.*

---

## 1. Package overview

This workspace contains a complete, cross-referenced knowledge corpus for the Australian insulation industry, organised into 7 layers:

| # | Layer | Location | Primary use |
|---|-------|----------|-------------|
| 1 | Broad expertise | `AU_Insulation_Expert_Knowledge_Base.md` | System prompt / persona |
| 2 | Compliance | `compliance/` | RAG knowledge base |
| 3 | Product intelligence | `product_intelligence/` | RAG knowledge base |
| 4 | Principles | `principles/` | RAG knowledge base |
| 5 | Customer support | `customer_support/` | RAG + fine-tuning |
| 6 | Training data | `training/` | Fine-tuning (JSONL) |
| 7 | Tools | `tools/` | Reference (interactive) |

---

## 2. Fine-tuning dataset

**File:** `training/qa_pairs.jsonl` — 88 question-answer pairs in OpenAI chat format.

```json
{"messages": [
  {"role": "system", "content": "You are an expert on Australian building insulation, NCC compliance, and thermal/acoustic principles."},
  {"role": "user", "content": "..."},
  {"role": "assistant", "content": "..."}
]}
```

**Also available:** `training/qa_pairs.json` (structured JSON) and `training/05_qa_pairs.md` (human-readable).

**Topic coverage (88 pairs):**
- Sound Insulation (13), Products & Manufacturers (11), Condensation (10), Materials (9), Climate Zones (9), NCC 2025 Commercial/Whole-of-Home (8), Fundamentals (7), NCC & Compliance (7), Energy Efficiency (6), Installation (5), Bushfire (3).

---

## 3. RAG knowledge base (chunkable markdown)

| File | Content | Approx. size |
|------|---------|--------------|
| `AU_Insulation_Expert_Knowledge_Base.md` | Industry overview, manufacturers, principles | 535 lines |
| `compliance/01_condensation_management.md` | Condensation, vapour permeance, mould index | 202 lines |
| `compliance/02_sound_transmission.md` | Sound, Rw+Ctr, discontinuous construction | 184 lines |
| `compliance/03_ncc_energy_efficiency.md` | 7-star, R-values, Section J, whole-of-home | 231 lines |
| `compliance/04_industry_reports.md` | AIIC policy, state performance | 99 lines |
| `compliance/05_standards_reference.md` | Standards, VCM classes, climate zones | 94 lines |
| `product_intelligence/01_manufacturers_suppliers.md` | 11+ manufacturers, brands, warranties | 259 lines |
| `product_intelligence/02_products_application.md` | Products by application + R-values | 183 lines |
| `product_intelligence/03_materials_applications.md` | 10 materials, properties, selection | 251 lines |
| `principles/01_thermal_principles.md` | Heat transfer, R/U-value, bridging | 293 lines |
| `principles/02_acoustic_principles.md` | Sound, mass law, ratings, flanking | 301 lines |
| `customer_support/01_top_50_customer_problems.md` | 50 problems + resolution | 277 lines |
| `customer_support/02_quick_triage.md` | Symptom → cause → solution | 60 lines |
| `training/01_glossary.md` | 120+ terms | 127 lines |
| `training/02_climate_zone_guide.md` | Per-zone strategy | 166 lines |
| `training/03_installation_guide.md` | Installation best practice | 115 lines |
| `training/04_bushfire.md` | AS 3959 BAL | 69 lines |

**Raw source text** (for deeper retrieval): `compliance/raw/` (7 files — full ABCB handbook text + NCC extracts).

---

## 4. Recommended training recipe

### Option A — RAG (recommended, fastest to deploy)
1. Chunk all markdown files (sections 3 above) into ~500-token chunks.
2. Embed with a sentence-transformer or API embedding model.
3. Store in a vector DB (Pinecone, Weaviate, Chroma, etc.).
4. At inference: retrieve top-k chunks + inject into prompt with the system persona.

### Option B — Fine-tuning (for a specialised, lightweight model)
1. Use `training/qa_pairs.jsonl` (88 pairs) as the seed.
2. Optionally augment with synthetic variations (paraphrase each Q/A 3–5×).
3. Fine-tune a small model (Llama 3 8B, Mistral 7B, etc.).
4. Combine with RAG for factual grounding (fine-tuning alone won't cover everything).

### Option C — Hybrid (best results)
- Fine-tune for tone/format + RAG for facts. This is the recommended production approach.

---

## 5. System prompt (persona)

```
You are an expert on Australian building insulation. You know the National Construction Code (NCC 2022/2025), Australian Standards (AS/NZS 4859, AS 4200, AS 3959), insulation products and manufacturers (CSR Bradford, Fletcher, Knauf, Kingspan, ROCKWOOL, Autex), and thermal and acoustic principles. You give accurate, practical advice for the Australian context — climate zones 1–8, condensation management, sound insulation, and energy efficiency. Always specify R-values in m²·K/W and reference the relevant NCC clause or standard where applicable.
```

---

## 6. Data freshness & caveats

- Compiled September 2026. NCC 2025 is current; NCC 2022 7-star adopted nationally by May 2025 (WA last).
- R-values shown are DTS minimums — a 7-star NatHERS assessment may require higher values.
- Climate zone boundaries and BAL ratings must be verified against official ABCB/local council sources for critical compliance.
- Re-verify against the ABCB website before formal compliance advice.

---

## 7. Regeneration

The `qa_pairs.json` and `qa_pairs.jsonl` are generated from `training/05_qa_pairs.md` by a Python script (pypdf + json). To regenerate after adding Q&A pairs, re-run the parser over the updated markdown.
