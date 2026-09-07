# Learning Model & Multi-Site Chatbot — Design Plan

Status: **P0 Complete** (2026-09-07). P1–P5 proposed.

This plan turns the current single-machine demo into a multi-site embedded chatbot with a
real learning loop, without weakening [`BOT_POLICY.md`](BOT_POLICY.md).

## Governing constraint

> **Learning may change ranking and language. It may never change authority.**

The learned model reorders candidates and phrases replies. It never selects a SKU, never
asserts NCC/AS/BAL/fire compliance, and never promotes a family that
`bot_engine.recommendation_allowed()` has blocked. Those remain deterministic, tested gates.

## Decisions taken

| Decision | Choice |
|---|---|
| Inference | Hybrid — retrieval, ranking and gating self-hosted; hosted LLM for phrasing and grounded answers only |
| Bot scope | Broaden what it **answers** (RAG, size lookups, free-text intake); keep what it **does** limited to qualification + callback. No quoting, no selling |
| Tenancy | Same full catalogue on every site; branding, greeting, contact routing and consent text differ per site |
| Provider | Abstracted behind `llm_client.py`. Gemini is the least-friction hosted backend (auth path already exists in `scripts/gemini_research_agent.py`) |

---

## Current state (verified, 2026-09-07)

**Working well**
- ~314 families over 26 manufacturers, with per-family TDS research JSON carrying source URLs and identity verification.
- `knowledge/industry/` — compliance, principles, product intelligence, 50-problem triage, 88 Q&A pairs already in chat-JSONL format.
- `bot_engine.py` — deterministic, tested, auditable ranking + evidence gate.
- `web_agent.py` — FastAPI serving surface with iframe embed.

**P0 COMPLETE (2026-09-07)**
- **Retrieval hygiene:** 236 research JSONs cleaned (2,500 terms dropped/salvaged), ingesters protected, ranker protected. 15 tests passing.
- **Retrieval cards:** 283 embedding-ready cards in `data/processed/retrieval_cards.jsonl`.
- **Gold-label template:** 240 real enquiries in `data/local/gold_labels_todo.csv` (local-only, awaiting labeller).
- **Persona:** "The Site Sage" wired into `llm_client.py` as a tone overlay beneath policy guardrails (`AGENT_PERSONA=off` kill-switch). 8 tests passing.
- **Test suite:** Full 49 passing (fixed pytest temp dir issue; removed committed `.pytest-tmp` junk tree).

**Four remaining gaps** (no work done on these yet)

1. **The learning loop is write-only.** `interaction_store.py` records outcomes
   (`approved`/`edited`/`rejected` + `corrected_family_id`) and `web_agent.py` reports them,
   but no call site reads outcomes back into ranking. It is telemetry, not learning.

2. **Retrieval is bag-of-words only.** No embeddings in the repo. P1 will build the dense
   channel and the eval harness to measure accuracy gain.

3. **`web_agent.py` is single-tenant and unauthenticated.** `_SESSIONS` is an in-process dict
   (one worker only, unbounded, lost on restart); no site concept; no CORS allowlist; no rate
   limiting; and `/api/learning/*` exposes conversation contents and accepts outcome writes
   with no auth. P2 hardens this for multi-site deployment.

4. **Bot scope is qualification + callback only.** It cannot answer informational questions
   ("what is an R-value?") or look up availability mid-conversation. P3 adds RAG, size
   lookups, and a router. Policy lint lands with P3 to guard all generated text.

---

## Target architecture

```
                        ┌──────────────────────────────────────┐
  site A ──┐            │  L5  Multi-site serving              │
  site B ──┼── widget ──►     site config · CORS · API keys    │
  site C ──┘            │     persistent sessions · rate limit  │
                        └──────────────┬───────────────────────┘
                                       ▼
                        ┌──────────────────────────────────────┐
                        │  L3  Router                          │
                        │  informational │ product-fit │ size  │
                        │  commercial → hand off │ escalate    │
                        └───┬───────────────┬──────────────┬───┘
                            ▼               ▼              ▼
              ┌─────────────────┐  ┌────────────────┐  ┌──────────┐
              │ RAG over        │  │ L1 hybrid      │  │ size_    │
              │ knowledge/      │  │ retrieval      │  │ index    │
              │ industry/**     │  │ lexical+dense  │  └──────────┘
              └────────┬────────┘  └───────┬────────┘
                       │                   ▼
                       │           ┌────────────────┐
                       │           │ L2 learned     │  shadow first
                       │           │ reranker       │
                       │           └───────┬────────┘
                       │                   ▼
                       │           ┌────────────────┐
                       │           │ evidence gate  │  UNCHANGED
                       │           │ bot_engine     │
                       │           └───────┬────────┘
                       ▼                   ▼
                     ┌──────────────────────────────┐
                     │  L4  policy lint (blocking)  │
                     │  fail → deterministic text   │
                     └──────────────────────────────┘
```

### L0 — Corpus hygiene (✓ COMPLETE)

**Delivery:**
- `retrieval_hygiene.py` — shared validation rules for all retrieval fields
- `scripts/clean_retrieval_fields.py` — one-pass cleanup + audit trail
- Applied to 236 research JSONs: ~2,500 terms dropped/salvaged, none lost to false positive
- `ingest_knowledge_base_txt.py` and `studio_batch.py` now clean at ingest-time
- `agent_core.load_families()` protected by `ranker_safe_terms()` at merge time
- 15 unit tests on edge cases (line-wrap artifacts, label bleed, fragments, mojibake)
- Full test suite: **49 passing**

**Outcome:** Pollution purged from the ranker's keyword/application/not_for feeds. Future ingests arrive clean. The reranker will train on curated terms, not noise.

### L1 — Hybrid retrieval

- **Keep `bot_engine.rank_families` untouched** as the lexical channel. It stays the audited
  fallback if the dense channel is unavailable.
- Dense channel: embed the ~314 retrieval cards locally (`nomic-embed-text` via Ollama, or
  `bge-small-en-v1.5`). 314 vectors needs no vector DB — a numpy array in memory is enough.
  Persist to `data/processed/family_embeddings.npz`, keyed by content hash so it rebuilds
  only when cards change.
- Fuse with **Reciprocal Rank Fusion** (`score = Σ 1/(60 + rank_i)`). RRF is scale-free, so
  the two channels need no score calibration against each other.
- `recommendation_allowed()` and `reliable_match` still apply *after* fusion.

### L2 — The learning model (learned reranker)

- **Model class:** LightGBM `lambdarank`, or plain logistic regression while data is thin.
  Deliberately **not** a neural reranker — label volume will be small for months and the
  ranking must stay auditable.
- **Features** (all interpretable, all already computable): lexical `match_score`, dense
  cosine similarity, RRF rank, keyword-hit count, application-hit count, priority score for
  the detected priority, placement adjustment, `not_for` hit count, evidence confidence state,
  climate zone, project type, new-vs-retrofit, detected element, family prior frequency.
- **Labels from `interaction_store`:**
  - `approved` on family F → positive `(conversation, F)`
  - `rejected` → negative `(conversation, F)`
  - `edited` with `corrected_family_id = G` → negative `(conversation, F)` **and** positive
    `(conversation, G)`

  This is precisely why `corrected_family_id` was worth storing.
- **Cold start** (you have ~zero interactions today):
  1. Hand-label the existing 150 scenarios with the correct family — roughly one afternoon of
     a sales engineer's time. *This is the labelled enquiry set `IMPLEMENTATION_STATUS.md`
     requires before embeddings are allowed.*
  2. Generate ~5 synthetic customer complaints per family from its retrieval card via the
     hosted LLM, **human-reviewed in batches**, giving ~1,500 weak-labelled pairs. Tag
     `source='synthetic'` and weight below real outcomes so real data dominates as it arrives.
- **Shadow mode first.** The reranker scores every conversation and logs its ranking, but the
  *displayed* recommendation stays the hybrid/deterministic one. Both are stored on the
  conversation record. Promote only when held-out top-1 accuracy beats the deterministic
  baseline by a meaningful margin **and** every safety metric is unchanged.
- **The reranker cannot learn the gate.** It reorders only within families that already pass
  `recommendation_allowed()`. Enforced in code, not by training.

### L3 — Routing and grounded answering

Router classifies each message: `informational` / `product-fit` / `size-availability` /
`commercial` / `escalate`. Start with rules (reuse `eval_scenarios.NON_PRODUCT_HINTS` and
`agent_core._SIZE_Q_RE`), upgrade to an LLM classifier with the rules as fallback.

- `informational` → RAG over `knowledge/industry/**`, heading-aware ~500-token chunks, same
  embedding index, top-k 6. Hosted LLM generates with **mandatory citations** to source files,
  and must refuse when retrieval confidence is weak. This is the capability the bot lacks
  entirely today — it currently cannot answer "what is an R-value?" at all.
- `size-availability` → promote the existing `agent_core.answer_size_query` path to work
  mid-conversation, not only after completion.
- `commercial` (price, stock, quantity, freight) → hand off, never answer. Already the
  documented expectation in `eval_scenarios.py`.
- `escalate` → BOT_POLICY escalation triggers (NCC, fire, BAL, performance targets, sensitive
  buildings) route straight to a person.

The 88 `qa_pairs.jsonl` serve as both RAG corpus and the seed evaluation set for the router
and the answerer — they are already in `messages` format.

### L4 — Policy lint (blocking, deterministic)

Every generated string passes `scripts/policy_lint.py` before reaching a customer:

- reject if it names a SKU, grade, thickness, density, facing, size or quantity;
- reject if it asserts NCC / Australian Standard / BAL / fire compliance, or guarantees a
  result (phrase list lifted directly from BOT_POLICY's "Not allowed" section);
- reject if it names a family other than the gated recommendation.

On failure → fall back to deterministic template text. This mirrors the safe-fallback pattern
`llm_client.phrase()` already uses. Extend `tests/test_llm_client.py` with cases built from
BOT_POLICY's own allowed/not-allowed examples.

### L5 — Multi-site serving

Given *same catalogue, different branding*, tenancy is configuration — not data partitioning.

- `config/sites/<site_id>.json` — display name, colours, logo, greeting, contact routing
  (phone, hours, callback wording), consent/privacy text, allowed origins, optional
  manufacturer **emphasis** (a soft ranking boost, never a hard filter).
- `web_agent.py` — `site_id` on every request; CORS allowlist assembled from site configs;
  per-site API key required on `/api/learning/*` (currently wide open); per-IP+site rate limit.
- **Sessions** — move `_SESSIONS` out of the process dict into SQLite (or Redis) with TTL
  eviction, so restarts don't drop conversations and more than one worker can run.
- **Embed** — ship `static/widget.js` for
  `<script src="https://your-host/widget.js" data-site-id="acme"></script>`, injecting a
  shadow-DOM launcher bubble around the existing iframe. Keeps iframe isolation, adds
  per-site theming.
- Add `site_id` to the `conversations` table so per-site performance is measurable.

---

## Evaluation — what makes this a learning *system*

Upgrade `scripts/eval_scenarios.py` from heuristics to **gold-label** scoring:

| Metric | Target |
|---|---|
| Top-1 family accuracy | beat deterministic baseline |
| Top-3 family accuracy | beat deterministic baseline |
| Blocked-family leak rate | **0** |
| Compliance-claim rate (policy lint) | **0** |
| Correct handoff on commercial questions | ~100% |
| RAG citation validity | every claim traceable |

Runs in CI on every ranker/config/knowledge change — `.github/workflows/ci.yml` already exists,
so this slots into the current release rule. Weekly retrain → shadow eval → **human
promotion**. Never auto-promote.

---

## Sequencing

| Phase | Work | Why here |
|---|---|---|
| **P0** | Corpus hygiene, retrieval cards, 150 gold labels | Everything downstream inherits this data. Shipping on polluted keywords bakes in the noise |
| **P1** | Hybrid retrieval + gold-label eval harness | Measurable accuracy win, low risk, satisfies the documented precondition for embeddings |
| **P2** | Multi-site hardening: sessions, auth, CORS, widget | Ships the product; independent of any ML work |
| **P3** | Router + RAG answering + policy lint | Biggest capability jump; policy lint must land with it, not after |
| **P4** | Learned reranker in shadow mode | Needs P0–P1 data and P1 eval to be meaningful |
| **P5** | Promotion criteria + weekly retrain loop | Closes the loop that `interaction_store` was built for |

P0 and P1 should land before anything customer-facing. P2 can run in parallel — it touches
serving, not modelling.

## Open items for owner decision

- Hosted-LLM privacy: customer wording leaves your server under the hybrid choice. Needs a DPA
  / privacy-notice decision and per-site consent text before P3 goes live.
- Retention policy for conversation logs used as training data (`AUDIT_SECURITY.md` covers
  callback PII; training-corpus retention is not yet specified).
- Who is the named authorised reviewer for outcome labelling, given BOT_POLICY reserves
  evidence verification to named reviewers.
