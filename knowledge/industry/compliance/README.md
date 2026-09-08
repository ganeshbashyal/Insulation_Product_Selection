# Australian Insulation Compliance — Knowledge Index

This folder contains digested compliance artifacts for Australian insulation, sourced from the ABCB (National Construction Code and handbooks) and the Affiliated Insulation Industry Coalition (AIIC). Designed for future bot/agent ingestion.

## Digested summaries (primary reading)

| File | Topic | Source |
|------|-------|--------|
| [01_condensation_management.md](01_condensation_management.md) | Condensation management — NCC Part F8/H4/10.8, vapour permeance, mould index, control layers | ABCB Condensation in buildings handbook (v4.0, NCC 2025) |
| [02_sound_transmission.md](02_sound_transmission.md) | Sound insulation — NCC Part F7/H4/10.7, Rw+Ctr, Ln,w, discontinuous construction | ABCB Sound Transmission handbook (v4.3) |
| [03_ncc_energy_efficiency.md](03_ncc_energy_efficiency.md) | Energy efficiency & thermal insulation — 7-star, Part 13.2/Section J, R-values, thermal bridging | NCC 2025 Volumes One & Two |
| [04_industry_reports.md](04_industry_reports.md) | Industry policy & market — AIIC recommendations, state performance, market data | AIIC reports 2024–2025 |
| [05_standards_reference.md](05_standards_reference.md) | Standards reference — all AS/NZS standards, VCM classes, climate zones | Compiled |

## Raw extracted text (reference)

| File | Source |
|------|--------|
| [raw/condensation_handbook.txt](raw/condensation_handbook.txt) | ABCB Condensation handbook (full text, 87 pages) |
| [raw/sound_handbook.txt](raw/sound_handbook.txt) | ABCB Sound Transmission handbook (full text, 89 pages) |
| [raw/ncc_vol2_housing.txt](raw/ncc_vol2_housing.txt) | NCC 2025 Volume Two — relevant pages (housing provisions) |
| [raw/ncc_vol1_commercial.txt](raw/ncc_vol1_commercial.txt) | NCC 2025 Volume One — relevant pages (Section J, F7, F8) |
| [raw/aiic_insulation_2024.txt](raw/aiic_insulation_2024.txt) | AIIC Insulation in Australia 2024 |
| [raw/aiic_traffic_light_2025.txt](raw/aiic_traffic_light_2025.txt) | AIIC Traffic Light Report 2025 |
| [raw/aiic_policy_2024.txt](raw/aiic_policy_2024.txt) | AIIC Policy Statement 2024 |

## Retrieval status

All files in this folder — the digested summaries **and** the raw extracted
text — are chunked into
[../training/compliance_rag_chunks.jsonl](../training/compliance_rag_chunks.jsonl)
by `scripts/build_compliance_chunks.py`, and loaded at runtime by
`rag_answerer.py`. 868 chunks; 540 carry an NCC clause identifier.

Chunking preserves the `===== PAGE n =====` markers as `page_start`/`page_end`
and extracts clause ids (`H4D9`, `F8D6`, `Part 10.8`, `J1D5`) into a `clauses`
field, so a retrieved chunk cites a locatable place in the source rather than a
filename. Re-run after editing anything here:

```powershell
python scripts/build_compliance_chunks.py --summary
```

> Before this was built, none of this folder reached the bot: the retriever's
> only `.txt` glob was non-recursive and matched nothing, so ~1.3 MB of primary
> compliance text — including both NCC volumes — was indexed nowhere.

## Version note

The raw extracts are **NCC 2025**, which supersedes NCC 2022. Where a document
elsewhere in this repo cites "NCC 2022", treat these extracts as the newer
source and re-check the clause. Clause identifiers were renumbered between
editions (NCC 2019 `3.8.7` → NCC 2022/2025 `H4D9` + Housing Provisions `10.8`).

## Source PDFs (original artifacts)

Downloaded to session scratchpad (`downloads/`):
- NCC2025_Condensation_Handbook.pdf (4.9 MB)
- Sound_Transmission_Handbook_2022.pdf (2.3 MB)
- NCC2025_Volume_One.pdf (61 MB)
- NCC2025_Volume_Two.pdf (29 MB)
- NCC2025_Volume_Three.pdf (30 MB)
- AIIC_Insulation_Australia_2024.pdf (770 KB)
- AIIC_Traffic_Light_2025.pdf (307 KB)
- AIIC_Policy_Statement_2024.pdf (404 KB)

## Related

- [../AU_Insulation_Expert_Knowledge_Base.md](../AU_Insulation_Expert_Knowledge_Base.md) — full industry knowledge base (manufacturers, products, principles)
