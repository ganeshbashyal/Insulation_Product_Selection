# Bot Training Dataset — Index

*Structured, machine-ingestible data for training/fine-tuning an Australian insulation bot.*

## Dataset contents

| File | Format | Purpose |
|------|--------|---------|
| [01_glossary.md](01_glossary.md) | Markdown | Terminology (120+ terms) for consistent vocabulary |
| [02_climate_zone_guide.md](02_climate_zone_guide.md) | Markdown | Detailed insulation strategy per NCC climate zone |
| [03_installation_guide.md](03_installation_guide.md) | Markdown | Installation best practice + common mistakes |
| [04_bushfire.md](04_bushfire.md) | Markdown | AS 3959 BAL requirements for insulation |
| [05_qa_pairs.md](05_qa_pairs.md) | Markdown | 88 Q&A pairs (human-readable) |
| [qa_pairs.json](qa_pairs.json) | JSON | 88 Q&A pairs (structured) |
| [qa_pairs.jsonl](qa_pairs.jsonl) | JSONL | 88 Q&A pairs in OpenAI chat format (fine-tuning-ready) |
| [expert_corpus.json](expert_corpus.json) | JSON | Deep expert corpus: 7 modules × 44 records with content, key points, Q&A and sources |
| [expert_finetune.jsonl](expert_finetune.jsonl) | JSONL | 133 chat-format pairs (45 corpus + 88 legacy, deduped) — generated |
| [expert_rag_chunks.jsonl](expert_rag_chunks.jsonl) | JSONL | 44 retrieval chunks with module/kind/sources metadata + content hash — generated |
| [expert_training_report.json](expert_training_report.json) | JSON | Coverage report (per-module counts, kind histogram) — generated |
| [building_class_rag_chunks.jsonl](building_class_rag_chunks.jsonl) | JSONL | 232 retrieval chunks covering NCC building-class construction staging — generated, **loaded at runtime by `rag_answerer.py`** |
| `building_class_finetune.jsonl` | JSONL | 850 chat-format pairs from the building-class profiles — generated, git-ignored, **unreviewed** |
| [building_class_training_report.json](building_class_training_report.json) | JSON | Building-class coverage report (per-class profile/element counts) — generated |
| [compliance_rag_chunks.jsonl](compliance_rag_chunks.jsonl) | JSONL | 868 retrieval chunks from the raw NCC/ABCB corpus + curated markdown — generated, **loaded at runtime** |

### Compliance dataset

The primary compliance sources — NCC 2025 Volumes One and Two, the ABCB
condensation and sound handbooks, AIIC industry reports — plus the curated
markdown under `compliance/`, `principles/`, `product_intelligence/` and
`customer_support/`. Rebuild with:

```powershell
python scripts/build_compliance_chunks.py --summary
```

| Source | Chunks |
|---|---|
| NCC Volume One (commercial) | 280 |
| Curated knowledge base | 277 |
| ABCB handbooks | 166 |
| NCC Volume Two (housing) | 108 |
| Industry reports | 37 |

540 of the 868 carry an extracted NCC clause id (`H4D9`, `F8D6`, `Part 10.8`),
and raw-source chunks keep their page numbers, so citations point at a
locatable place in the source document.

> None of this reached the bot before 2026-09-08: the retriever globbed
> `*.txt` non-recursively at the top of `knowledge/industry/`, which matched
> nothing, so ~1.3 MB of primary compliance text was indexed nowhere. The
> corpus went from 276 chunks to 1,144.

### Building-class dataset

Covers what is built at each construction stage per NCC class (1–10c), and
where insulation, membranes and fire/acoustic materials are installed. Source
of truth is `knowledge/building_classes/building_class_source.json`; edit that,
not the outputs, then re-run:

```powershell
python -m construction_ingest.building_class --export-json --export-training --summary
```

36 profiles → 196 stages → 338 insulation elements. The same command loads them
into SQLite with an FTS5 index for direct querying (`--lookup 9b`, `--search soffit`).

> The fine-tune pairs assert NCC clauses taken verbatim from the source and have
> **not** been used to train anything. Review them before any model repeats those
> clauses as fact. Retrieval is doing the work today, not fine-tuning.

### Retrieval quality (measured 2026-09-08)

Measured by `scripts/eval_knowledge_retrieval.py`, which derives its own ground
truth from the corpus, so no hand labelling is needed. All local — embeddings
and generation both via Ollama.

| Metric | Result |
|---|---|
| recall@1 | 83.2% |
| recall@5 | 98.7% |
| MRR | 0.903 |
| answers generated | 100% |
| answers citing a source | 100% |

Remaining recall@1 misses are near-ties between genuinely similar profiles
(e.g. two separate Class 9b assembly-building profiles), not wrong-class matches.

*Generated files are built by `scripts/build_expert_training_data.py` from `expert_corpus.json`; edit the corpus, not the outputs, then re-run:*

```powershell
python scripts/build_expert_training_data.py --include-legacy-qa   # validate + rebuild
python scripts/build_expert_training_data.py --validate-only       # check without writing
```

The validator enforces unique record IDs, required fields, non-empty Q&A, and per-record sources.
`--strict` promotes warnings (thin content, missing sources) to errors.

## Q&A dataset statistics

- **88 question-answer pairs** across 11 topics:
  - Sound Insulation (13)
  - Products & Manufacturers (11)
  - Condensation Management (10)
  - Materials (9)
  - Climate Zones (9)
  - NCC 2025 Commercial & Whole-of-Home (8)
  - Fundamentals & General (7)
  - NCC & Compliance (7)
  - Energy Efficiency & Thermal (6)
  - Installation (5)
  - Bushfire (3)

## JSONL format (fine-tuning-ready)

Each line is an OpenAI-style chat message:
```json
{"messages": [
  {"role": "system", "content": "You are an expert on Australian building insulation, NCC compliance, and thermal/acoustic principles."},
  {"role": "user", "content": "What is an R-value?"},
  {"role": "assistant", "content": "R-value is thermal resistance..."}
]}
```

## How to use for bot training

1. **Fine-tuning:** use `qa_pairs.jsonl` directly (OpenAI chat format) — ready for OpenAI/GPT, Llama, or other fine-tuning pipelines.
2. **RAG (retrieval-augmented generation):** `rag_answerer.py` loads `qa_pairs.jsonl` plus every `training/*_rag_chunks.jsonl` automatically, embeds them with local Ollama and caches the vectors. Dropping a new `*_rag_chunks.jsonl` here is enough to put it in front of the bot; only the first run pays the embedding cost.
3. **System prompt:** the master [README.md](../README.md) and [AU_Insulation_Expert_Knowledge_Base.md](../AU_Insulation_Expert_Knowledge_Base.md) provide the bot's persona and domain framing.

## Full corpus (all layers)

| Layer | Folder | Content |
|-------|--------|---------|
| Broad expertise | `../AU_Insulation_Expert_Knowledge_Base.md` | Industry overview |
| Compliance | `../compliance/` | NCC/ABCB digests + raw text |
| Product intelligence | `../product_intelligence/` | Manufacturers, products, materials |
| Principles | `../principles/` | Thermal & acoustic physics |
| Customer support | `../customer_support/` | 50 problems + triage |
| Tools | `../tools/` | Interactive compliance tool |
| Training data | `./` (this folder) | Glossary, guides, Q&A pairs |
