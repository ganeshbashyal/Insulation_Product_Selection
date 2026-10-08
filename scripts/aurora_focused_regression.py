"""Run a local-only, resumable Aurora regression for concept answers and closure."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import sys
import tempfile
import time
from types import SimpleNamespace
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import agent_core
import interaction_store
import llm_client
import local_model
import research_store
from conversation_service import ConversationService
from router import MessageRouter
from scripts.aurora_learning_eval import _append_jsonl, _read_jsonl, _require_ignored_output, _safe_customer_message

MODEL = "llama3.2:latest"
RUN_ID_DEFAULT = "aurora-focused-regression-remediation-v3"
SCHEMA_VERSION = 1
BATCH_SIZE_DEFAULT = 10
CASE_REPEATS = 8
SCENARIOS = (
    {
        "id": "r-value",
        "kind": "concept",
        "prompt": "What does R-value mean for insulation?",
        "required_terms": ("thermal resistance",),
        "disallowed_phrases": ("which product do you mean", "not enough relevant local information"),
        "setup": None,
    },
    {
        "id": "thermal-bridging",
        "kind": "concept",
        "prompt": "Can you explain thermal bridging in plain language?",
        "required_terms": ("heat flow", "bypassing"),
        "disallowed_phrases": ("which product do you mean", "not enough relevant local information"),
        "setup": None,
    },
    {
        "id": "sarking",
        "kind": "concept",
        "prompt": "What is sarking used for under a roof?",
        "required_terms": ("membrane",),
        "disallowed_phrases": ("which product do you mean", "not enough relevant local information"),
        "setup": None,
    },
    {
        "id": "thanks-standalone",
        "kind": "closure",
        "prompt": "Thanks, that's all I needed. I'm done for now.",
        "required_terms": (),
        "disallowed_phrases": ("where is the insulation needed", "what are you working on"),
        "setup": None,
    },
    {
        "id": "thanks-during-discovery",
        "kind": "closure",
        "prompt": "I appreciate your help; that's everything I needed for now.",
        "required_terms": (),
        "disallowed_phrases": ("where is the insulation needed", "what are you working on"),
        "setup": "My external wall is cold",
    },
    {
        "id": "thanks-courtesy-control",
        "kind": "courtesy",
        "prompt": "Thanks for your help.",
        "required_terms": (),
        "disallowed_phrases": (),
        "setup": "My external wall is cold",
    },
)
MAX_CASES = CASE_REPEATS * len(SCENARIOS)
GENERATOR_SYSTEM = (
    "You rewrite synthetic customer messages for a local insulation assistant regression test. "
    "Do not answer the customer. Preserve the exact intent and topic. Do not add any names, "
    "contact details, measurements, product names, or extra project facts. Return only one "
    "short, single-line customer message."
)


def evaluation_tasks(*, seed: int, count: int = MAX_CASES) -> list[dict]:
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_CASES:
        raise ValueError(f"Evaluation count must be an integer from 1 to {MAX_CASES}")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("Evaluation seed must be a non-negative integer")
    tasks = []
    for scenario in SCENARIOS:
        for variation in range(CASE_REPEATS):
            key = f"{seed}:{scenario['id']}:{variation}"
            tasks.append({
                "scenario": scenario,
                "variation": variation,
                "session_id": hashlib.sha256(key.encode("utf-8")).hexdigest()[:20],
            })
    random.Random(seed).shuffle(tasks)
    return tasks[:count]


def _variant_seed(seed: int, task: dict) -> int:
    raw = f"{seed}:{task['session_id']}:paraphrase".encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:4], "big") & 0x7FFFFFFF


def _preserves_intent(text: str, scenario: dict) -> bool:
    folded = text.casefold()
    if scenario["kind"] == "concept":
        term_pattern = {
            "r-value": r"\br[\s-]?value\b",
            "thermal-bridging": r"\bthermal\s+bridg(?:e|ing)\b",
            "sarking": r"\bsarking\b",
        }[scenario["id"]]
        return bool(re.search(term_pattern, folded))
    has_acknowledgement = bool(re.search(r"\b(?:thanks?|appreciate|grateful)\b", folded))
    has_closure = bool(re.search(r"\b(?:all|everything|done|finished|nothing else|no more|for now)\b", folded))
    if scenario["kind"] == "courtesy":
        return has_acknowledgement and not has_closure
    return has_acknowledgement and has_closure


def _make_paraphrase(task: dict, *, seed: int, model: str) -> dict:
    scenario = task["scenario"]
    variant_seed = _variant_seed(seed, task)
    candidate = llm_client.generate_reply(
        GENERATOR_SYSTEM,
        f"Rewrite this synthetic customer message with natural wording while preserving its intent:\n"
        f"{scenario['prompt']}",
        max_tokens=64,
        timeout=60,
        model=model,
        seed=variant_seed,
    )

    message, rejection = _safe_customer_message(candidate, scenario["prompt"])
    if rejection is None and not _preserves_intent(message, scenario):
        rejection = "paraphrase did not preserve the scenario intent"
    if rejection is not None:
        return {
            "message": scenario["prompt"],
            "status": "template_fallback",
            "reason": rejection,
            "seed": variant_seed,
            "candidate": candidate,
        }
    return {
        "message": message,
        "status": "generated",
        "reason": None,
        "seed": variant_seed,
    }


def _check_response(task: dict, result, conversation, before: dict | None) -> dict:
    scenario = task["scenario"]
    text = result.reply.casefold()
    checks = {}
    if scenario["kind"] == "concept":
        checks["informational_route"] = result.category == "informational"
        checks["local_glossary_retrieval"] = result.retrieval_mode == "local-glossary"
        checks["source_citation"] = any(
            line.strip().casefold().startswith("source:")
            for line in result.reply.splitlines()
        )
        checks["answer_is_direct"] = not any(
            phrase in text for phrase in scenario["disallowed_phrases"]
        )
        checks["key_concepts_present"] = all(term in text for term in scenario["required_terms"])
        checks["no_unrequested_product_answer"] = not any(
            family.get("name", "").casefold() in text
            for family in agent_core.FAMILIES
            if family.get("name")
        )
        checks["no_specific_product_rating"] = not bool(
            re.search(r"\b(?:r[\s-]?value|rw|nrc)\s*(?:of|is|:)?\s*\d+(?:\.\d+)?\b", text)
        )
    elif scenario["kind"] == "closure":
        checks["closure_route"] = result.category == "greeting"
        checks["no_new_intake_prompt"] = not any(
            phrase in text for phrase in scenario["disallowed_phrases"]
        )
        checks["no_question_after_explicit_close"] = "?" not in result.reply
        checks["no_recommendation"] = conversation.recommendation is None
        checks["conversation_not_finalized"] = not getattr(conversation, "done", False)
        if before is not None:
            checks["discovery_facts_preserved"] = conversation.answers == before["answers"]
            checks["pending_question_not_advanced"] = conversation.pending_field == before["pending_field"]
            checks["discovery_status_preserved"] = (
                conversation.discovery_status == before["discovery_status"]
            )
            checks["lead_state_preserved"] = getattr(conversation, "lead", {}) == before["lead"]
    else:
        checks["greeting_route"] = result.category == "greeting"
        checks["pending_question_repeated"] = "?" in result.reply
        checks["no_recommendation"] = conversation.recommendation is None
        if before is not None:
            checks["discovery_facts_preserved"] = conversation.answers == before["answers"]
            checks["pending_question_not_advanced"] = conversation.pending_field == before["pending_field"]
            checks["discovery_status_preserved"] = (
                conversation.discovery_status == before["discovery_status"]
            )
            checks["lead_state_preserved"] = getattr(conversation, "lead", {}) == before["lead"]
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
    }


def _write_report(output: Path, manifest: dict, sessions: list[dict], *, batch_count: int) -> dict:
    scenarios_by_id = {scenario["id"]: scenario for scenario in SCENARIOS}
    completed = [row for row in sessions if row.get("status") == "complete"]
    for row in completed:
        scenario = scenarios_by_id[row["scenario_id"]]
        final_turn = row["transcript"][-1]
        final_state = final_turn["state"]
        conversation = SimpleNamespace(
            answers=final_state.get("answers", {}),
            pending_field=final_state.get("pending_field"),
            recommendation=object() if final_state.get("recommendation_present") else None,
            discovery_status=final_state.get("discovery_status", {}),
            lead=final_state.get("lead", {}),
            done=final_state.get("done", False),
        )
        before = None
        if scenario["setup"]:
            setup_state = row["transcript"][0]["state"]
            before = {
                "answers": setup_state.get("answers", {}),
                "pending_field": setup_state.get("pending_field"),
                "discovery_status": setup_state.get("discovery_status", {}),
                "lead": setup_state.get("lead", {}),
            }
        result = SimpleNamespace(
            reply=final_turn["reply"],
            category=final_turn["category"],
            retrieval_mode=final_turn["retrieval_mode"],
        )
        row["evaluation"] = _check_response(
            {"scenario": scenario},
            result,
            conversation,
            before,
        )
    scenario_stats = {}
    for scenario in SCENARIOS:
        rows = [row for row in completed if row["scenario_id"] == scenario["id"]]
        scenario_stats[scenario["id"]] = {
            "sessions": len(rows),
            "passed": sum(row["evaluation"]["passed"] for row in rows),
            "failed": sum(not row["evaluation"]["passed"] for row in rows),
            "failures": dict(Counter(
                failure for row in rows for failure in row["evaluation"]["failures"]
            )),
            "generator_fallbacks": sum(
                row["paraphrase"]["status"] != "generated" for row in rows
            ),
        }
    model_failures = Counter(
        call["failure"]
        for row in completed
        for call in row.get("model_calls", [])
        if call.get("failure")
    )
    model_call_counts = Counter(
        call.get("role", "unknown")
        for row in completed
        for call in row.get("model_calls", [])
    )
    model_call_seconds = Counter()
    for row in completed:
        for call in row.get("model_calls", []):
            if isinstance(call.get("seconds"), (int, float)):
                model_call_seconds[call.get("role", "unknown")] += float(call["seconds"])
    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": manifest["run_id"],
        "seed": manifest["seed"],
        "model": manifest["model"],
        "target_sessions": manifest["target_sessions"],
        "completed_sessions": len(completed),
        "passed_sessions": sum(row["evaluation"]["passed"] for row in completed),
        "failed_sessions": sum(not row["evaluation"]["passed"] for row in completed),
        "batch_completed_sessions": batch_count,
        "scenario_results": scenario_stats,
        "model_calls_by_role": dict(model_call_counts),
        "model_call_seconds_by_role": {
            role: round(seconds, 2) for role, seconds in model_call_seconds.items()
        },
        "model_call_failures": dict(model_failures),
        "generator_fallbacks": sum(row["paraphrase"]["status"] != "generated" for row in completed),
        "incomplete_attempts": sum(row.get("status") != "complete" for row in sessions),
        "run_status": "complete" if len(completed) == manifest["target_sessions"] else "in_progress",
        "note": (
            "Synthetic local evaluation only. Deterministic checks govern pass/fail; "
            "model-generated inputs are advisory test variation, not customer evidence."
        ),
    }
    sessions_text = "".join(
        json.dumps(row, ensure_ascii=False) + "\n"
        for row in sessions
    )
    (output / "sessions.jsonl").write_text(sessions_text, encoding="utf-8")
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _write_learning_plan(output / "learning_plan.md", report)
    return report


def _write_learning_plan(path: Path, report: dict) -> None:
    results = report["scenario_results"]
    lines = [
        "# Aurora focused regression findings",
        "",
        f"- Run: `{report['run_id']}` (seed `{report['seed']}`)",
        f"- Status: {report['run_status']}; completed {report['completed_sessions']} / {report['target_sessions']}.",
        f"- Deterministic results: {report['passed_sessions']} passed, {report['failed_sessions']} failed.",
        f"- Local model-call failures: {report['model_call_failures'] or 'none'}.",
        f"- Paraphrase fallbacks: {report['generator_fallbacks']}.",
        "",
        "## Results by focus",
        "",
    ]
    for scenario_id, summary in report["scenario_results"].items():
        lines.append(
            f"- `{scenario_id}`: {summary['passed']}/{summary['sessions']} passed; "
            f"failures: {summary['failures'] or 'none'}; "
            f"paraphrase fallbacks: {summary['generator_fallbacks']}."
        )
    lines.extend((
        "",
        "## Prioritized regression signals",
        "",
        f"1. **Sarking concept answers:** {results['sarking']['failed']}/"
        f"{results['sarking']['sessions']} failed. Review transcripts for "
        "any remaining mismatch between the glossary definition and its citation.",
        f"2. **General R-value answers:** {results['r-value']['failed']}/"
        f"{results['r-value']['sessions']} failed. Review generic-definition "
        "coverage separately from product-specific verified-value requests.",
        f"3. **Conversation closure:** {results['thanks-standalone']['failed']}/"
        f"{results['thanks-standalone']['sessions']} standalone and "
        f"{results['thanks-during-discovery']['failed']}/"
        f"{results['thanks-during-discovery']['sessions']} active-discovery "
        "cases failed. Review whether explicit finality is acknowledged without "
        "advancing the partial enquiry.",
        f"4. **Thermal-bridging control:** {results['thermal-bridging']['passed']}/"
        f"{results['thermal-bridging']['sessions']} passed. Preserve this direct "
        "glossary answer and source citation during follow-up changes.",
        f"5. **Courtesy-only thanks control:** {results['thanks-courtesy-control']['passed']}/"
        f"{results['thanks-courtesy-control']['sessions']} passed. Preserve the "
        "pending question without recording the courtesy phrase as an answer.",
        "",
        "## Interpretation",
        "",
        "These are synthetic paraphrase results, not production-customer "
        "evidence. The model endpoint had no recorded call failures; "
        f"{report['generator_fallbacks']} inputs used fixed-template fallbacks. "
        "The observed deterministic quality failures are valid follow-up signals, "
        "not an instruction to change production behavior automatically. No "
        "Aurora production behavior was changed by this run.",
        "",
    ))
    path.write_text("\n".join(lines), encoding="utf-8")


def run_evaluation(
    *,
    output_dir: Path,
    run_id: str,
    count: int = MAX_CASES,
    batch_size: int | None = None,
    seed: int = 20261009,
    model: str = MODEL,
    require_git_ignored: bool = True,
    progress_callback=None,
) -> dict:
    if batch_size is not None and (
        isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1
    ):
        raise ValueError("batch_size must be a positive integer")
    tasks = evaluation_tasks(seed=seed, count=count)
    output_dir = output_dir.resolve()
    if require_git_ignored:
        _require_ignored_output(output_dir)
    base = local_model.loopback_ollama_base()
    parsed = urlsplit(base)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Focused regression requires a loopback-only Ollama endpoint")
    installed = local_model.chat_models()
    if model not in installed:
        raise RuntimeError(
            f"Required local chat model is not installed: {model}; no downloads were attempted"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    sessions_path = output_dir / "sessions.jsonl"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "seed": seed,
        "target_sessions": count,
        "model": model,
        "scenario_repeats": CASE_REPEATS,
        "scenario_ids": [scenario["id"] for scenario in SCENARIOS],
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        for key in ("schema_version", "run_id", "seed", "target_sessions", "model", "scenario_repeats", "scenario_ids"):
            if existing.get(key) != manifest[key]:
                raise RuntimeError(f"Cannot resume focused run: manifest field {key!r} does not match")
        manifest = existing
    elif sessions_path.exists():
        raise RuntimeError("Focused trace exists without a manifest; refusing to overwrite or append")
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    prior = _read_jsonl(sessions_path)
    completed_ids = {
        row.get("session_id") for row in prior
        if row.get("status") == "complete" and isinstance(row.get("session_id"), str)
    }
    attempts = Counter(row.get("session_id") for row in prior)
    available = [task for task in tasks if task["session_id"] not in completed_ids]
    selected = available[:batch_size] if batch_size is not None else available
    original_interaction_db = interaction_store.DEFAULT_DB
    original_research_db = research_store.DEFAULT_DB
    original_generate = llm_client.generate_reply
    started = time.monotonic()
    completed_this_batch = 0
    endpoint_failure_streak = 0
    all_sessions = list(prior)

    try:
        with tempfile.TemporaryDirectory(prefix="aurora-focused-regression-") as directory:
            interaction_store.DEFAULT_DB = Path(directory) / "interactions.sqlite3"
            research_store.DEFAULT_DB = Path(directory) / "research.sqlite3"
            for task in selected:
                scenario = task["scenario"]
                attempt = attempts[task["session_id"]] + 1
                model_calls = []
                current_role = ["paraphrase"]

                def measured_generate(*args, **kwargs):
                    started_call = time.monotonic()
                    answer = None
                    failure = None
                    try:
                        answer = original_generate(*args, **kwargs)
                        failure = llm_client._MODEL_CALL_FAILURE.get()
                        return answer
                    finally:
                        model_calls.append({
                            "role": current_role[0],
                            "model": kwargs.get("model") or llm_client._MODEL_OVERRIDE.get() or llm_client.OLLAMA_MODEL,
                            "seconds": round(time.monotonic() - started_call, 3),
                            "responded": bool(answer),
                            "failure": failure or llm_client._MODEL_CALL_FAILURE.get(),
                            "num_thread": llm_client._GENERATION_THREADS.get(),
                            "seed": kwargs.get("seed", llm_client._GENERATION_SEED.get()),
                        })

                llm_client.generate_reply = measured_generate
                call_context = llm_client.using_model(
                    model,
                    seed=_variant_seed(seed, task),
                    local_only=True,
                    num_thread=2,
                )
                with call_context:
                    paraphrase = _make_paraphrase(task, seed=seed, model=model)
                    current_role[0] = "aurora"
                    service = ConversationService(
                        use_llm=True,
                        router=MessageRouter(use_llm=True),
                    )
                    conversation = agent_core.Conversation()
                    transcript = []
                    setup_result = None
                    if scenario["setup"]:
                        setup_result = service.handle(
                            conversation, scenario["setup"], site_id=f"eval-{task['session_id']}"
                        )
                        transcript.append({
                            "role": "customer",
                            "message": scenario["setup"],
                            "reply": setup_result.reply,
                            "category": setup_result.category,
                            "retrieval_mode": setup_result.retrieval_mode,
                            "turn": 0,
                            "state": {
                                "mode": conversation.mode,
                                "pending_field": conversation.pending_field,
                                "answers": dict(conversation.answers),
                                "discovery_status": dict(conversation.discovery_status),
                                "lead": dict(conversation.lead),
                                "done": conversation.done,
                            },
                        })
                        conversation = agent_core.Conversation.from_dict(conversation.to_dict())
                    before = {
                        "answers": dict(conversation.answers),
                        "pending_field": conversation.pending_field,
                        "discovery_status": dict(conversation.discovery_status),
                        "lead": dict(conversation.lead),
                    } if scenario["setup"] else None
                    current_role[0] = "aurora"
                    result = service.handle(
                        conversation,
                        paraphrase["message"],
                        site_id=f"eval-{task['session_id']}",
                    )
                    transcript.append({
                        "role": "customer",
                        "message": paraphrase["message"],
                        "reply": result.reply,
                        "category": result.category,
                        "retrieval_mode": result.retrieval_mode,
                        "source_references": [
                            line.strip() for line in result.reply.splitlines()
                            if line.strip().casefold().startswith("source:")
                        ],
                        "human_review_required": result.human_review_required,
                        "review_labels": list(result.review_labels),
                        "turn": len(transcript),
                        "state": {
                            "mode": conversation.mode,
                            "pending_field": conversation.pending_field,
                            "answers": dict(conversation.answers),
                            "discovery_status": dict(conversation.discovery_status),
                            "lead": dict(conversation.lead),
                            "done": conversation.done,
                            "recommendation_present": conversation.recommendation is not None,
                        },
                    })
                    evaluation = _check_response(task, result, conversation, before)
                    failed_calls = [call for call in model_calls if call.get("failure")]
                    endpoint_failure_streak = endpoint_failure_streak + 1 if failed_calls else 0
                    session = {
                        "schema_version": SCHEMA_VERSION,
                        "run_id": run_id,
                        "session_id": task["session_id"],
                        "attempt": attempt,
                        "scenario_id": scenario["id"],
                        "kind": scenario["kind"],
                        "variation": task["variation"],
                        "status": "complete",
                        "paraphrase": paraphrase,
                        "model_calls": list(model_calls),
                        "transcript": transcript,
                        "evaluation": evaluation,
                        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    }
                llm_client.generate_reply = original_generate
                _append_jsonl(sessions_path, session)
                all_sessions.append(session)
                completed_ids.add(task["session_id"])
                completed_this_batch += 1
                if progress_callback is not None:
                    progress_callback(
                        len(completed_ids),
                        count,
                        task,
                        evaluation,
                        paraphrase,
                    )
                if endpoint_failure_streak >= 2:
                    break
    finally:
        llm_client.generate_reply = original_generate
        interaction_store.DEFAULT_DB = original_interaction_db
        research_store.DEFAULT_DB = original_research_db

    report = _write_report(
        output_dir,
        manifest,
        all_sessions,
        batch_count=completed_this_batch,
    )
    report["batch_elapsed_seconds"] = round(time.monotonic() - started, 2)
    report["endpoint_failure_streak"] = endpoint_failure_streak
    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _write_learning_plan(output_dir / "learning_plan.md", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=RUN_ID_DEFAULT)
    parser.add_argument("--count", type=int, default=MAX_CASES)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE_DEFAULT)
    parser.add_argument("--seed", type=int, default=20261009)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    output_dir = args.output_dir or (
        ROOT / "data" / "local" / "evaluations" / "aurora-focused-regression" / args.run_id
    )

    def report_progress(completed, target, task, evaluation, paraphrase):
        print(
            f"{completed}/{target} | {task['scenario']['id']} | "
            f"input={paraphrase['status']} | "
            f"checks={'PASS' if evaluation['passed'] else 'FAIL:' + ','.join(evaluation['failures'])}",
            flush=True,
        )

    report = run_evaluation(
        output_dir=output_dir,
        run_id=args.run_id,
        count=args.count,
        batch_size=args.batch_size,
        seed=args.seed,
        model=args.model,
        progress_callback=report_progress,
    )
    print(
        f"{report['completed_sessions']}/{report['target_sessions']} complete; "
        f"{report['passed_sessions']} passed; {report['failed_sessions']} failed; "
        f"{report['generator_fallbacks']} input fallbacks"
    )
    print(f"Traces and report: {output_dir}")
    if report["run_status"] == "complete":
        return 0
    if report["endpoint_failure_streak"] >= 2:
        print("Stopped after repeated local model call failures; resume after Ollama is healthy.")
        return 2
    print(f"Batch complete ({report['batch_completed_sessions']} new cases); resume with the same settings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
