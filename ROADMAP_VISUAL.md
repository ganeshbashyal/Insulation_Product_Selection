# Local development roadmap

Last updated: 2026-09-13

The project is intentionally local-first. Core ranking, policy enforcement,
retrieval, audit storage, and validation must work without cloud infrastructure
or a running language model.

## Current state

| Area | State | Boundary |
|---|---|---|
| Family discovery | Operational | Deterministic ranking; family-level suggestions only |
| Qualification flow | Operational | `agent_core.Conversation` state served by the local FastAPI service |
| Informational retrieval | Operational | Dense retrieval when local Ollama is available; immediate lexical fallback otherwise |
| SKU lookup | Limited | Published eligible rows may be shown as possible matches; no automatic quoting or ordering |
| Human review | Operational | Local encrypted-capable SQLite queue |
| Interaction learning | Operational | Reviewer outcomes inform manual tuning only |
| Generated-data governance | Operational | CI checks checked-in runtime artifacts against local source records |
| Freight and tracking | Hand-off only | No carrier, ERP, or cloud connector |
| Production deployment | Not approved | Requires locally managed identity, TLS, secrets, monitoring, and backups |

## Delivery sequence

1. **Reliability baseline**
   - Keep the complete test and validation suite deterministic with Ollama stopped.
   - Treat startup latency, generated-artifact drift, and database migration failures as release blockers.

2. **Evidence maturity**
   - Resolve the items emitted by `python scripts/evidence_triage.py`.
   - Prioritise primary manufacturer evidence for high-volume and frequently requested families.
   - Preserve separate R, Rw, NRC/alpha-w, fire, vapour, and system scopes.

3. **Gated SKU matching**
   - Return only rows marked eligible by the SKU/evidence manifest.
   - Include source status and require human confirmation.
   - Do not infer quantities, installed performance, compliance, price, or availability.

4. **Local operations**
   - Add an approved local freight-rate table before calculating delivery costs.
   - Add an approved local order-status export before tracking orders.
   - Define backup, retention, encryption-key rotation, and restore procedures for local SQLite stores.

5. **Release readiness**
   - Exercise the full intake-to-review flow with representative labelled enquiries.
   - Record precision, no-match, escalation, and reviewer-correction rates.
   - Approve production behavior only after security and operational controls are implemented.

## Required local gate

```powershell
python scripts/validate_catalogue.py
python scripts/validate_aircall_pack.py
python scripts/check_generated_artifacts.py
python scripts/evidence_triage.py
python -m pytest -q
```
