# Construction ingestion engine

Zero-cloud-cost data pipeline for the Australian Construction AI Agent. All
processing is local: SQLite, plain `urllib`, and a self-hosted Ollama instance.
No OpenAI, Anthropic, or other paid cloud SDK is used anywhere in this package.

## Scope and limitation

Everything here is a **screening and conversation aid**, not a compliance
certificate. Two rules the code enforces deliberately:

- Climate-zone boundaries do not follow postcode boundaries. Every seeded
  lookup is flagged `requires_confirmation` and points at the
  [ABCB Climate Map](https://ncc.abcb.gov.au/abcb-climate-map).
- Required Total R-values are project-specific (building class, construction,
  compliance pathway, glazing and services trade-offs, state variations), so no
  per-zone R-value table is published. That number comes from the project energy
  assessment.

## Modules

| Module | Purpose |
| --- | --- |
| [db_setup.py](./db_setup.py) | Builds `data/construction_postcodes.db`: postcode → suburb, state, ABCB climate zone 1–8, NCC volume. Optional downloader for public postcode CSVs. |
| [construction_matrix.py](./construction_matrix.py) | Dataclasses and the populated `phase × framing × zone → material + NCC provision` matrix. |
| [local_pdf_parser.py](./local_pdf_parser.py) | Extracts TDS PDF text and structures it via local Ollama with Pydantic validation → `data/product_knowledge.json`. |
| [main.py](./main.py) | Unified runner: parses a question, resolves the zone, applies the rules and screens local products. |
| [building_class.py](./building_class.py) | Ingests NCC building-class construction profiles (stages, trades, insulation elements) into SQLite + FTS5, and exports RAG/fine-tune training data. |

## Quick start

```bash
pip install -r requirements.txt

# 1. Build everything (downloads a public postcode CSV; add --offline to skip)
python -m construction_ingest.main --build

# 2. Ask a question
python -m construction_ingest.main --query \
  "What wrap and insulation stage applies to a steel-framed house in postcode 3000 (Melbourne)?"

# 3. Built-in demo queries
python -m construction_ingest.main --demo
```

Flag-driven form, and JSON output for programmatic use:

```bash
python -m construction_ingest.main --postcode 7000 --framing steel --phase wrapping
python -m construction_ingest.main --query "steel frame in 3000" --json
```

## Data layers

### 1. Postcode → climate zone

Rows carry a `confidence` column:

- `authoritative` — loaded from a CSV that supplied a real ABCB climate-zone
  column. Suburb-level and cite-able.
- `range_seed` — derived from the coarse postcode-range table bundled in
  `db_setup.py`. A screening default only.

Authoritative rows always overwrite seeded rows for the same
`(postcode, suburb, state)`. A candidate zone column is rejected unless at
least 90% of its values parse as zones 1–8, which stops unrelated `*zone`
columns (for example an electricity `chargezone`) being ingested as climate data.

```bash
python -m construction_ingest.db_setup --csv path/to/abcb_climate_zones.csv
python -m construction_ingest.db_setup --offline --lookup 3000
python -m construction_ingest.db_setup --export-json data/postcode_zones.json
```

### 2. Construction matrix

Phases run `Slab → Framing → Wrapping → Insulation → Lining`. Every rule cites
its `provision`. The timber/steel distinction drives the matrix:

| | Timber | Steel (cold-formed) |
| --- | --- | --- |
| Conductivity | ≈ 0.12 W/mK | ≈ 50 W/mK (~400×) |
| Thermal break | none mandated | **continuous R0.2 minimum**, NCC 2022 Housing Provisions Part 13.2 |
| Batts | friction-fit between studs | sized to the steel stud module at 450/600 mm centres |
| Total R-value | framing fraction in the calculation | steel framing correction per AS/NZS 4859.2 |

Membrane requirements outside the primary wall insulation, per Housing
Provisions clause 10.8.1(2):

| Zones | Minimum vapour permeance | Classes |
| --- | --- | --- |
| 1–3 | no zone-specific minimum | Class 1–4 |
| 4–5 | 0.143 µg/N·s | Class 3, Class 4 |
| 6–8 | 1.14 µg/N·s | Class 4 |

Zones 6–8 also trigger the roof-space ventilation provisions in clause 10.8.3.

### 3. Local TDS ingestion

Drop manufacturer PDFs into `data/tds/` (searched recursively), then:

```bash
ollama serve
ollama pull llama3.2

python -m construction_ingest.local_pdf_parser --model llama3.2
python -m construction_ingest.local_pdf_parser --no-llm   # regex only
```

Text is extracted with `pdfplumber` (falling back to `pypdf`), pre-filled with
deterministic regex, then structured by the model with `format=json` and
validated by Pydantic. If Ollama is unreachable or times out, the run degrades
to the regex result and records the reason in `extraction_warnings` rather than
failing.

Configuration is by environment variable: `OLLAMA_HOST`, `OLLAMA_TDS_MODEL`
(or `OLLAMA_MODEL`), `OLLAMA_TIMEOUT_SECONDS`.

### 4. Building-class construction profiles

[building_class.py](./building_class.py) ingests NCC building-class profiles —
what gets built at each stage, and where insulation, membranes and fire/acoustic
materials go, per building class.

```bash
python -m construction_ingest.building_class \
    --source knowledge/building_classes/building_class_source.json \
    --export-json --export-training --summary

python -m construction_ingest.building_class --lookup 9b --no-ingest
python -m construction_ingest.building_class --search soffit --no-ingest
```

The source is tolerant of two quirks in the supplied data: it is a stream of
concatenated top-level objects rather than a JSON array, and it embeds LaTeX
fragments (`$Rw + Ctr \ge 50$`) inside string values, which is not legal JSON.
Both are repaired on read, so `\ge` becomes `>=` and the `$` delimiters are
dropped.

Element keys vary between profiles. Ten known keys are promoted to columns and
**every remaining key is preserved verbatim in `extra_json`**, so nothing in the
source is discarded.

It writes into the same `data/construction_postcodes.db`, adding
`building_class_profiles`, `building_class_stages`, `building_class_elements`,
`building_class_codes` and an FTS5 index `building_class_search`. The postcode
tables are untouched.

Class lookup follows NCC nesting: a bare number (`9`) matches every subclass,
and a subclass (`9b`) also matches profiles registered against the bare parent,
so a "Class 2 to Class 9" mixed-use profile is correctly returned for `9b`.

#### Training the local model on it

`--export-training` writes, into `knowledge/industry/training/`:

- `building_class_rag_chunks.jsonl` — one overview chunk per profile plus one
  per construction stage, in the repo's existing chunk format.
- `building_class_finetune.jsonl` — chat-format pairs for an optional local
  fine-tune.
- `building_class_training_report.json` — counts and the system prompt used.

`rag_answerer.py` loads any `*_rag_chunks.jsonl` in that directory, so the
chunks reach retrieval as soon as they are exported; embeddings are generated
locally through Ollama and cached, so only the first run is slow.

## Product screening

Products are never silently dropped. Anything failing the zone permeance
threshold or the framing compatibility check is returned with
`screening_status: flagged` and an explicit reason, so the operator can see why.
The pipeline never asserts that a product is NCC-compliant.

## Tests

```bash
python -m pytest tests/test_construction_ingest.py tests/test_building_class.py -q
```

The suite runs fully offline — no downloads and no Ollama calls.
