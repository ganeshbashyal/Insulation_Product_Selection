# Aurora local conversation evaluation

The synthetic evaluation runner exercises Aurora locally and keeps generated
conversation traces separate from customer, lead, and interaction stores.
Historical Aurora interactions are read-only and are used only as aggregate
scenario themes; no historical excerpts are replayed or copied into test data.

## Local prerequisites

- Ollama must already be installed and listening on loopback.
- The selected chat models must already be installed; the evaluation never
  downloads a model.
- The default roles are `llama3.2:latest` for Aurora's optional wording and
  `mistral:7b` for synthetic customer turns, with `phi4-mini:latest` for
  transcript critique. Phi 4 Mini was selected after a local timing/schema
  check: it produced a valid rubric response in about 14 seconds, versus about
  29 seconds for Mistral 7B on the same sample.
- The evaluator checks Ollama's chat-capable models and refuses non-loopback
  hosts. Evaluation calls disable proxies and HTTP redirects.
- Evaluation model calls are serial and capped at two inference threads to
  reduce sustained CPU impact on the workstation.

## Run safely

Start with a five- to ten-session pilot:

```powershell
python scripts/aurora_learning_eval.py --count 5 --run-id aurora-pilot
```

Only run the full 500-session matrix after checking the pilot's report, local
resource use, and model availability:

```powershell
python scripts/aurora_learning_eval.py --count 500 --run-id aurora-full
```

To release the evaluator process between smaller chunks, use `--batch-size`
with the same run ID and settings each time. Each invocation completes at most
that many new sessions, writes its current report, and can be safely resumed:

```powershell
python scripts/aurora_learning_eval.py --count 500 --run-id aurora-full --batch-size 25
```

Run that command again to continue until all 500 sessions are complete. The
two-thread inference limit remains in effect in every batch.

## Focused overnight regression

Use the focused runner for the conversation-quality signals found in the larger
synthetic run: direct answers to general insulation concepts and recognizing
explicit multiword closure. It exercises R-value, thermal bridging, and sarking
questions, plus explicit closure in fresh and active-discovery conversations
and a courtesy-only thanks control. Llama 3.2 generates safe synthetic
paraphrases; deterministic checks decide pass/fail, and no production behavior
is changed by evaluation.

Run up to 48 cases in resumable batches of 10 (the final batch contains 8).
Use a new run ID for remediation runs so existing traces remain unchanged.
Between invocations, wait one minute and inspect CPU and memory before starting
the next batch:

```powershell
python scripts/aurora_focused_regression.py --count 48 --batch-size 10 --run-id aurora-focused-regression-remediation-v3
Start-Sleep -Seconds 60
```

Repeat the command with the same run ID, seed, and model until the report shows
48 completed cases. Active-discovery explicit closure must leave captured facts
and the pending field unchanged; courtesy-only thanks should repeat the pending
question without recording thanks as a project fact. The runner stops after
repeated local model failures; resume only after loopback Ollama is healthy.
Full synthetic traces are saved under the Git-ignored
`data/local/evaluations/aurora-focused-regression/<run-id>/` directory.

Use the same `--run-id`, seed, count, and model choices for the runner being
resumed. Do not change these settings for an existing run. The 500-session
matrix defaults to seed `20261008`; the focused runner defaults to
`20261009`. Ollama generation calls receive stable per-turn seeds.
`--offline-deterministic` on the matrix runner disables all model calls and is
useful for validating scenario contracts without consuming model resources.

Output is written under the Git-ignored
`data/local/evaluations/aurora-learning/<run-id>/` directory:

- `manifest.json` records the run, seed, scenario count, model roles, and mode
  allocation.
- `sessions.jsonl` stores each session's full synthetic transcript, deterministic
  checks, local critic result, timing, and errors.
- `turns.jsonl` stores each user/assistant turn, route, retrieval/citation
  metadata, review labels, and state summary.
- `report.json` aggregates safety checks, scenario-oracle mismatches, turn
  position, unknown/skip handling, model timings, and critic scores. In
  chunked/resumed runs, `elapsed_seconds` and `batch_seconds_per_session`
  describe the latest invocation; `batch_completed_sessions` gives its sample
  size rather than implying an end-to-end runtime.
- `learning_plan.md` ranks findings for human review; it does not modify Aurora.

An interrupted partial final JSONL record is discarded on resume; complete
records remain intact. A model critic is advisory, not ground truth. Exact
dialogue-case expectations remain separate from hard safety checks when a
local model paraphrases a synthetic customer message.

## Pilot observations

The initial ten-session run took about 7.6 minutes end to end and accumulated
about 8.2 minutes of serialized Ollama call time; Mistral critique averaged
about 30 seconds, customer simulation 10 seconds, and Llama wording 6 seconds.
A subsequent five-session pilot completed in 4.4 minutes with all five
critiques parsed and no hard safety failures. A warm two-session integrated run
with Phi 4 Mini critique took about 25 seconds; a single cold critic benchmark
took about 14 seconds. During the first full run, `llama-server` used about 49%
of total 8-core CPU capacity, so the evaluation was stopped and resumed with
the two-thread limit. Runtime for 500 sessions is still measured in hours, not
minutes; check the run log and CPU/memory use during execution.
Scenario lengths, model loading, cache state, and other system work can change
the result. The pilot also showed why simulator outputs must not be graded
solely by exact template phrases; the runner reports those mismatches separately
from safety checks.
