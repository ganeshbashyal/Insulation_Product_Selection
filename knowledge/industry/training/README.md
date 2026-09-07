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
2. **RAG (retrieval-augmented generation):** chunk the markdown files (glossary, climate zones, installation, bushfire, plus the parent `compliance/`, `product_intelligence/`, and `principles/` folders) as the knowledge base.
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
