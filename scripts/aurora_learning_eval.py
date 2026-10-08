"""Run a local-only, resumable synthetic Aurora conversation evaluation."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import agent_core
import interaction_store
import llm_client
import local_model
from dialogue_cases import CASES, DialogueCase
from conversation_service import ConversationService
from scripts.eval_customer_conversations import evaluate_case

SCENARIO_GROUPS = (
    ("greeting-basics", ("greeting", "thanks", "insulation-definition", "insulation-work", "casual-definition")),
    ("thermal-concepts", ("r-value", "u-value", "total-r", "product-r", "thermal-bridge")),
    ("materials-and-products", ("sarking", "dew-point", "rw", "known-product", "product-use")),
    ("product-identity-and-context", ("manufacturer", "ambiguous-brand", "unknown-product", "missing-rating", "ambiguous-pronoun")),
    ("commercial-and-safety-boundaries", ("stock", "quantity", "price", "compliance", "install-service")),
    ("service-and-continuity", ("tracking", "freight", "remember-product", "change-product", "interrupt-name")),
    ("discovery-and-corrections", ("greet-then-select", "resume-name", "later-details", "correct-application", "requirements-answer")),
    ("handoff-and-construction", ("early-handoff", "decline-contact", "clarify-brief", "construction-preserved", "unknown-project-stage")),
    ("multi-detail-and-ambiguity", ("complete-volunteered-brief", "manufacturer", "known-product", "product-use", "ambiguous-brand")),
    ("evidence-and-interruption", ("missing-rating", "unknown-product", "ambiguous-pronoun", "compliance", "skip-project-stage")),
)
VARIATIONS = (
    "Use plain, everyday wording.",
    "Keep the same meaning in a concise conversational style.",
    "Sound friendly while staying factual.",
    "Use polite, natural wording without adding details.",
    "Use relaxed but clear wording.",
    "Be direct and brief.",
    "Sound slightly uncertain only if the source message is uncertain.",
    "Use a natural spoken word order.",
    "Keep the message simple and easy to understand.",
    "Use a different natural phrasing while preserving every fact and intent.",
)
MAX_CUSTOMER_TURNS = 8
SCHEMA_VERSION = 1
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)")
NAME_RE = re.compile(r"(?i)\b(?:my name is|name is|this is)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?")
CONTROL_MESSAGES = {
    "skip", "unknown", "i don't know", "no thanks", "finish now", "stop questions",
}


@dataclass(frozen=True)
class ScenarioCell:
    scenario_id: str
    group: str
    case: DialogueCase
    expected_discovery_status: tuple[str, str] | None = None


@dataclass(frozen=True)
class EvaluationTask:
    cell: ScenarioCell
    variation: int
    mode: str
    session_id: str


def scenario_cells() -> tuple[ScenarioCell, ...]:
    """Return 50 named evaluation cells backed by existing dialogue contracts."""
    by_name = {case.name: case for case in CASES}
    cells = []
    for group, case_names in SCENARIO_GROUPS:
        for index, name in enumerate(case_names, start=1):
            if name not in by_name:
                raise RuntimeError(f"Evaluation matrix references unknown dialogue case: {name}")
            expected_status = {
                "skip-project-stage": ("project_stage", "skipped"),
                "unknown-project-stage": ("project_stage", "unknown"),
            }.get(name)
            cells.append(
                ScenarioCell(
                    f"{group}-{index:02d}-{name}",
                    group,
                    by_name[name],
                    expected_discovery_status=expected_status,
                )
            )
    if len(cells) != 50:
        raise RuntimeError(f"Expected 50 evaluation scenario cells, found {len(cells)}")
    return tuple(cells)


def evaluation_tasks(*, seed: int, count: int = 500) -> list[EvaluationTask]:
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 500:
        raise ValueError("Evaluation count must be an integer from 1 to 500")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("Evaluation seed must be a non-negative integer")

    tasks = []
    for cell in scenario_cells():
        for variation in range(10):
            mode = "local-wording" if variation % 2 else "model-off"
            key = f"{seed}:{cell.scenario_id}:{variation}"
            session_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
            tasks.append(EvaluationTask(cell, variation, mode, session_id))
    rng = random.Random(seed)
    by_mode = {
        mode: [task for task in tasks if task.mode == mode]
        for mode in ("model-off", "local-wording")
    }
    for mode_tasks in by_mode.values():
        rng.shuffle(mode_tasks)
    balanced = []
    for index in range(max(len(rows) for rows in by_mode.values())):
        for mode in ("model-off", "local-wording"):
            if index < len(by_mode[mode]):
                balanced.append(by_mode[mode][index])
    return balanced[:count]


def _model_seed(seed: int, task: EvaluationTask, turn_number: int, purpose: str) -> int:
    key = f"{seed}:{task.session_id}:{turn_number}:{purpose}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(key).digest()[:4], "big") & 0x7FFFFFFF


def _safe_customer_message(candidate: str | None, source: str) -> tuple[str, str | None]:
    if not candidate:
        return source, "model returned no message"
    text = candidate.strip().strip('"“”\'` ')
    text = re.sub(r"^(?:customer|reply|message)\s*:\s*", "", text, flags=re.I).strip()
    if not text or len(text) > 320 or "\n" in text:
        return source, "model output was empty, multiline, or too long"
    if EMAIL_RE.search(text) and not EMAIL_RE.search(source):
        return source, "model introduced contact information"
    if PHONE_RE.search(text) and not PHONE_RE.search(source):
        return source, "model introduced contact information"
    if set(re.findall(r"\d+(?:\.\d+)?", text)) - set(re.findall(r"\d+(?:\.\d+)?", source)):
        return source, "model introduced a number not present in the scenario"
    if NAME_RE.search(text) and not NAME_RE.search(source):
        return source, "model introduced a name"
    for family in agent_core.FAMILIES:
        family_name = family.get("name", "")
        if family_name and family_name.casefold() in text.casefold() and family_name.casefold() not in source.casefold():
            return source, "model introduced a product-family name"
    return text, None


def _redact_for_critic(text: str) -> str:
    text = EMAIL_RE.sub("[synthetic contact]", text)
    text = PHONE_RE.sub("[synthetic contact]", text)
    return NAME_RE.sub("[synthetic name]", text)


def _parse_critique(text: str | None) -> tuple[dict | None, str | None]:
    if not text:
        return None, "model returned no critique"
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.I)
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None, "invalid_json"
    if not isinstance(payload, dict):
        return None, "invalid_shape"
    raw_scores = payload.get("scores")
    dimensions = ("relevance", "continuity", "naturalness", "evidence_care", "consent_and_review")
    if raw_scores is None:
        raw_scores = payload
    if not isinstance(raw_scores, dict):
        return None, "invalid_scores"
    scores = {}
    for dimension in dimensions:
        value = raw_scores.get(dimension)
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
            return None, f"invalid_score:{dimension}"
        scores[dimension] = value
    issues = payload.get("issues", [])
    if not isinstance(issues, list) or any(not isinstance(item, str) for item in issues):
        return None, "invalid_issues"
    summary = payload.get("summary", "")
    if not isinstance(summary, str):
        return None, "invalid_summary"
    clean_text = lambda value: PHONE_RE.sub(
        "[redacted contact]", EMAIL_RE.sub("[redacted contact]", value)
    )[:240]
    return {
        "scores": scores,
        "issues": [clean_text(item) for item in issues[:5]],
        "summary": clean_text(summary),
    }, None


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    content = path.read_bytes()
    if content and not content.endswith(b"\n"):
        lines = content.splitlines()
        try:
            json.loads(lines[-1].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            content = content[:content.rfind(b"\n") + 1] if b"\n" in content else b""
        else:
            content += b"\n"
        path.write_bytes(content)
    lines = content.decode("utf-8").splitlines()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            if line_number == len(lines):
                continue
            raise RuntimeError(f"Invalid JSONL at {path.name}:{line_number}") from exc
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _append_jsonl(path: Path, item: dict) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()


def _require_ignored_output(path: Path) -> None:
    try:
        relative = path.resolve().relative_to(ROOT.resolve())
    except ValueError as exc:
        raise RuntimeError("Evaluation traces must stay inside the repository's ignored local-data tree") from exc
    if relative.parts[:2] != ("data", "local"):
        raise RuntimeError("Evaluation traces must be written under data/local/")
    check = subprocess.run(
        ["git", "check-ignore", "--quiet", str(relative)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        raise RuntimeError("Evaluation output path is not Git-ignored; refusing to write transcripts")


def _make_customer_transform(
    *,
    task: EvaluationTask,
    seed: int,
    customer_model: str,
    local_models: bool,
    set_model_role,
):
    def transform(turn_number: int, template: str, transcript: list[dict]) -> tuple[str, dict]:
        if not local_models:
            return template, {"model": None, "status": "deterministic-template"}
        if template.strip().casefold() in CONTROL_MESSAGES or EMAIL_RE.search(template) or PHONE_RE.search(template):
            return template, {"model": customer_model, "status": "kept-control-or-contact-template"}

        history = [
            {"customer": row["customer"], "aurora": row["reply"]}
            for row in transcript[-4:]
        ]
        system_prompt = (
            "You are simulating a fictional insulation customer for an offline software test. "
            "Rewrite only the supplied customer message in the requested voice. Preserve its intent, "
            "all stated facts, uncertainty, and corrections exactly. Do not answer as Aurora, add any "
            "fact, product, name, address, phone number, email, or technical claim, or include labels. "
            "Return one short customer message only."
        )
        user_prompt = json.dumps({
            "voice": VARIATIONS[task.variation],
            "prior_synthetic_turns": history,
            "customer_message_to_rephrase": template,
        }, ensure_ascii=False)
        set_model_role("customer-simulator")
        with llm_client.using_model(
            customer_model,
            seed=_model_seed(seed, task, turn_number, "customer"),
            local_only=True,
            num_thread=2,
        ):
            response = llm_client.generate_reply(
                system_prompt,
                user_prompt,
                max_tokens=90,
                num_ctx=4096,
                timeout=120,
                model=customer_model,
            )
        generated, rejection = _safe_customer_message(response, template)
        return generated, {
            "model": customer_model,
            "status": "generated" if rejection is None else "template-fallback",
            "fallback_reason": rejection,
        }

    return transform


def _critique(
    transcript: list[dict],
    *,
    task: EvaluationTask,
    seed: int,
    critic_model: str,
    local_models: bool,
    set_model_role,
) -> tuple[dict | None, str | None]:
    if not local_models:
        return None, "critic_not_requested"
    safe_transcript = [
        {
            "customer": _redact_for_critic(turn["customer"]),
            "aurora": turn["reply"],
            "category": turn["category"],
            "retrieval_mode": turn["retrieval_mode"],
            "human_review_required": turn["human_review_required"],
        }
        for turn in transcript
    ]
    system_prompt = (
        "You are a critic of a fictional customer-support dialogue in an offline evaluation. "
        "Judge the full exchange, not whether you agree with product claims. Never quote or repeat "
        "customer text or personal/contact data. Treat deterministic safety checks as authoritative. "
        "Return only JSON with scores (integer 1-5) for relevance, continuity, naturalness, "
        "evidence_care, consent_and_review; issues (up to three short strings); and a one-sentence summary. "
        "Do not recommend a product or weaken consent, evidence, or human-review requirements."
    )
    user_prompt = json.dumps({
        "scenario_group": task.cell.group,
        "variation": VARIATIONS[task.variation],
        "transcript": safe_transcript,
    }, ensure_ascii=False)
    parse_error = None
    for attempt in range(2):
        set_model_role("transcript-critic")
        retry_prompt = user_prompt
        if attempt:
            retry_prompt += (
                "\n\nReturn valid JSON only. The scores must be an object named `scores` with "
                "exactly the five requested dimensions and integer values from 1 through 5. "
                "Include `issues` as an array and `summary` as a short string."
            )
        with llm_client.using_model(
            critic_model,
            seed=_model_seed(seed, task, MAX_CUSTOMER_TURNS + attempt, "critic"),
            local_only=True,
            num_thread=2,
        ):
            response = llm_client.generate_reply(
                system_prompt,
                retry_prompt,
                max_tokens=260,
                num_ctx=4096,
                timeout=180,
                model=critic_model,
            )
        critique, parse_error = _parse_critique(response)
        if critique is not None:
            critique["retry_count"] = attempt
            return critique, None
    return None, parse_error


def _summarize(sessions: list[dict], *, run_id: str, seed: int, target_count: int) -> dict:
    complete = [row for row in sessions if row.get("status") == "complete"]
    failures = Counter(
        failure
        for row in complete
        for failure in row.get("evaluation", {}).get("failures", [])
    )
    expectation_mismatches = Counter(
        mismatch
        for row in complete
        for mismatch in row.get("evaluation", {}).get("scenario_expectation_mismatches", [])
    )
    ranked_failures = []
    for failure, count in failures.items():
        high_impact = any(
            term in failure.casefold()
            for term in ("recommendation", "candidate leaked", "approval", "consent", "compliance", "evidence", "review")
        )
        high_confidence = any(
            term in failure.casefold()
            for term in ("recommendation", "candidate leaked", "approval", "consent", "expected discovery status")
        )
        ranked_failures.append({
            "failure": failure,
            "count": count,
            "safety_impact": "high" if high_impact else "medium",
            "confidence": "high" if high_confidence else "medium",
        })
    ranked_failures.sort(
        key=lambda item: (
            item["safety_impact"] == "high",
            item["count"],
            item["confidence"] == "high",
        ),
        reverse=True,
    )
    modes = {}
    for mode in ("model-off", "local-wording"):
        subset = [row for row in complete if row.get("mode") == mode]
        modes[mode] = {
            "sessions": len(subset),
            "passed": sum(bool(row.get("evaluation", {}).get("passed")) for row in subset),
            "critic_valid": sum(row.get("critique") is not None for row in subset),
            "average_turns": round(
                sum(len(row.get("evaluation", {}).get("transcript", [])) for row in subset) / len(subset),
                2,
            ) if subset else 0,
        }
    scenario_stats: dict[str, dict] = {}
    turn_stats: dict[str, dict] = defaultdict(
        lambda: {"turns": 0, "human_review_turns": 0, "seconds_total": 0.0}
    )
    status_counts = Counter()
    for row in complete:
        evaluation = row.get("evaluation", {})
        scenario_id = row.get("scenario_id", "unknown")
        scenario = scenario_stats.setdefault(
            scenario_id,
            {
                "scenario_group": row.get("scenario_group"),
                "sessions": 0,
                "passed": 0,
                "failed": 0,
                "failures": Counter(),
                "expectation_mismatches": Counter(),
            },
        )
        scenario["sessions"] += 1
        scenario["passed"] += int(bool(evaluation.get("passed")))
        scenario["failed"] += int(not bool(evaluation.get("passed")))
        scenario["failures"].update(evaluation.get("failures", []))
        scenario["expectation_mismatches"].update(
            evaluation.get("scenario_expectation_mismatches", [])
        )
        final_state = evaluation.get("final_state", {})
        status_counts.update(final_state.get("discovery_status", {}).values())
        for index, turn in enumerate(evaluation.get("transcript", []), start=1):
            turn_stat = turn_stats[str(index)]
            turn_stat["turns"] += 1
            turn_stat["human_review_turns"] += int(bool(turn.get("human_review_required")))
            turn_stat["seconds_total"] += float(turn.get("seconds", 0))
    for scenario in scenario_stats.values():
        scenario["failures"] = dict(scenario["failures"].most_common())
        scenario["expectation_mismatches"] = dict(scenario["expectation_mismatches"].most_common())
        scenario["pass_rate"] = round(scenario["passed"] / scenario["sessions"], 3)
    by_turn = {
        turn: {
            "turns": stats["turns"],
            "human_review_turns": stats["human_review_turns"],
            "average_seconds": round(stats["seconds_total"] / stats["turns"], 3),
        }
        for turn, stats in sorted(turn_stats.items(), key=lambda item: int(item[0]))
    }
    dimension_values: dict[str, list[int]] = defaultdict(list)
    critic_retries = 0
    for row in complete:
        critique = row.get("critique") or {}
        critic_retries += int(critique.get("retry_count", 0))
        for dimension, score in critique.get("scores", {}).items():
            dimension_values[dimension].append(score)
    model_errors = Counter(
        call.get("role", "unknown")
        for row in complete
        for call in row.get("model_calls", [])
        if not call.get("responded")
    )
    model_failure_reasons: dict[str, Counter] = defaultdict(Counter)
    for row in complete:
        for call in row.get("model_calls", []):
            if not call.get("responded"):
                model_failure_reasons[call.get("role", "unknown")][
                    call.get("failure") or "unspecified"
                ] += 1
    latency_by_role: dict[str, list[float]] = defaultdict(list)
    customer_simulation_statuses = Counter(
        turn.get("customer_simulation", {}).get("status", "unknown")
        for row in complete
        for turn in row.get("evaluation", {}).get("transcript", [])
    )
    for row in complete:
        for call in row.get("model_calls", []):
            if isinstance(call.get("seconds"), (int, float)):
                latency_by_role[call.get("role", "unknown")].append(float(call["seconds"]))
    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "seed": seed,
        "target_sessions": target_count,
        "completed_sessions": len(complete),
        "passed_sessions": sum(bool(row.get("evaluation", {}).get("passed")) for row in complete),
        "failed_sessions": sum(not bool(row.get("evaluation", {}).get("passed")) for row in complete),
        "critic_valid_sessions": sum(row.get("critique") is not None for row in complete),
        "critic_retries": critic_retries,
        "customer_simulation_statuses": dict(customer_simulation_statuses),
        "model_errors_by_role": dict(model_errors),
        "model_failure_reasons": {
            role: dict(reasons.most_common())
            for role, reasons in model_failure_reasons.items()
        },
        "model_average_seconds_by_role": {
            role: round(sum(values) / len(values), 2)
            for role, values in latency_by_role.items() if values
        },
        "model_call_count_by_role": {
            role: len(values) for role, values in latency_by_role.items()
        },
        "deterministic_failures": dict(failures.most_common()),
        "ranked_failures": ranked_failures,
        "scenario_expectation_mismatches": dict(expectation_mismatches.most_common()),
        "by_mode": modes,
        "by_scenario": scenario_stats,
        "by_turn_position": by_turn,
        "discovery_status_counts": {
            "unknown": status_counts["unknown"],
            "skipped": status_counts["skipped"],
        },
        "average_turns": round(
            sum(len(row.get("evaluation", {}).get("transcript", [])) for row in complete) / len(complete),
            2,
        ) if complete else 0,
        "critic_average_scores": {
            dimension: round(sum(values) / len(values), 2)
            for dimension, values in dimension_values.items() if values
        },
        "incomplete_attempts": sum(row.get("status") != "complete" for row in sessions),
        "completed_scenario_groups": dict(Counter(row["scenario_group"] for row in complete)),
        "note": (
            "This is synthetic local evaluation, not production-customer evidence. "
            "A model critic is advisory and deterministic policy/evidence checks plus human review govern."
        ),
    }
    return report


def _write_learning_plan(path: Path, report: dict) -> None:
    failures = report["ranked_failures"]
    lines = [
        "# Aurora synthetic evaluation learning plan",
        "",
        f"- Run: `{report['run_id']}` (seed `{report['seed']}`)",
        f"- Completed: {report['completed_sessions']} / {report['target_sessions']}",
        f"- Deterministic pass: {report['passed_sessions']} passed, {report['failed_sessions']} failed",
        f"- Valid local-model critiques: {report['critic_valid_sessions']}",
        "",
        "## Ranked observations",
        "",
    ]
    if failures:
        for rank, item in enumerate(failures, start=1):
            lines.append(
                f"{rank}. **{item['failure']}** — observed in {item['count']} conversation(s); "
                f"safety impact: {item['safety_impact']}; confidence: {item['confidence']}. "
                "Inspect the affected Aurora routing, state, wording, retrieval, or policy path; "
                "add a deterministic regression before changing behavior."
            )
    elif report["completed_sessions"]:
        lines.append(
            "1. No deterministic contract failures were recorded. Review a stratified sample of transcripts "
            "and any low-scoring critic dimensions before concluding that the flow is natural."
        )
    else:
        lines.append("No conversations completed; resolve the recorded local-run failure before drawing conclusions.")
    lines.extend(("", "## Model-critic signals", ""))
    if report["critic_average_scores"]:
        for dimension, score in sorted(report["critic_average_scores"].items(), key=lambda item: item[1]):
            lines.append(f"- `{dimension}` average: {score}/5 (advisory only).")
    else:
        lines.append("- No valid critique scores were available.")
    lines.extend(("", "## Scenario expectation mismatches", ""))
    if report["scenario_expectation_mismatches"]:
        for mismatch, count in report["scenario_expectation_mismatches"].items():
            lines.append(
                f"- {count} mismatch(es): `{mismatch}`. Interpret alongside the generated customer wording; "
                "the fixed-case oracle is diagnostic when the simulator paraphrases its prompt."
            )
    else:
        lines.append("- No scenario expectation mismatches were recorded.")
    lines.extend(("", "## Baseline comparison", ""))
    for mode, summary in report["by_mode"].items():
        lines.append(
            f"- `{mode}`: {summary['passed']}/{summary['sessions']} deterministic passes; "
            f"average {summary['average_turns']} turns per session."
        )
    lines.extend((
        f"- Discovery fields marked unknown: {report['discovery_status_counts']['unknown']}.",
        f"- Discovery fields skipped: {report['discovery_status_counts']['skipped']}.",
        f"- Model calls needing critic retry: {report['critic_retries']}.",
        f"- Synthetic customer simulator outcomes: {report['customer_simulation_statuses'] or 'none'}.",
        "",
        "## Scenario cells for manual review",
        "",
    ))
    lowest_scenarios = sorted(
        report["by_scenario"].items(),
        key=lambda item: (item[1]["pass_rate"], -item[1]["failed"], item[0]),
    )[:10]
    if lowest_scenarios:
        for scenario_id, summary in lowest_scenarios:
            lines.append(
                f"- `{scenario_id}` — {summary['passed']}/{summary['sessions']} passed "
                f"({summary['pass_rate']:.0%}); hard failures: {summary['failures'] or 'none'}; "
                f"template-oracle mismatches: {summary['expectation_mismatches'] or 'none'}."
            )
    else:
        lines.append("- No scenario results are available.")
    lines.extend((
        "",
        "## Next actions",
        "",
        "1. Manually review a stratified sample of failures, model disagreements, and low-rated transcripts.",
        "2. Rank confirmed causes by safety impact, frequency, and confidence; assign each to a code layer.",
        "3. Add the reviewed failing conversations as regression tests, then rerun the same seeded matrix.",
        "4. Do not apply model-critic suggestions or alter production behavior without human review.",
        "",
        "All transcripts and supporting traces are synthetic and local. Historical conversations were used only as aggregate themes.",
        "",
    ))
    path.write_text("\n".join(lines), encoding="utf-8")


def run_evaluation(
    *,
    output_dir: Path,
    run_id: str,
    count: int = 500,
    seed: int = 20261008,
    aurora_model: str = "llama3.2:latest",
    customer_model: str = "mistral:7b",
    critic_model: str = "phi4-mini:latest",
    local_models: bool = True,
    require_git_ignored: bool = True,
    max_new_sessions: int | None = None,
    progress_callback=None,
) -> dict:
    """Run or resume a synthetic evaluation; never writes to operational stores."""
    if max_new_sessions is not None and max_new_sessions < 1:
        raise ValueError("max_new_sessions must be at least 1")
    tasks = evaluation_tasks(seed=seed, count=count)
    if not local_models:
        tasks = [replace(task, mode="model-off") for task in tasks]
    output_dir = output_dir.resolve()
    if require_git_ignored:
        _require_ignored_output(output_dir)
    available_models: set[str] = set()
    if local_models:
        available_models = set(local_model.chat_models())
        missing = {aurora_model, customer_model, critic_model} - available_models
        if missing:
            raise RuntimeError(
                "Required local models are not installed; no downloads were attempted: "
                + ", ".join(sorted(missing))
            )
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    sessions_path = output_dir / "sessions.jsonl"
    turns_path = output_dir / "turns.jsonl"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "seed": seed,
        "target_sessions": count,
        "scenario_cells": 50,
        "variations_per_cell": 10,
        "models": {
            "aurora": aurora_model if local_models else None,
            "customer_simulator": customer_model if local_models else None,
            "critic": critic_model if local_models else None,
        },
        "mode_allocation": (
            "balanced seeded sample; the full 500-session matrix has five sessions per mode per scenario cell"
            if local_models else "all sessions model-off; all local model calls disabled"
        ),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        for key in ("schema_version", "run_id", "seed", "target_sessions", "scenario_cells", "variations_per_cell", "models"):
            if existing.get(key) != manifest[key]:
                raise RuntimeError(f"Cannot resume run: manifest field {key!r} does not match")
    else:
        if sessions_path.exists() or turns_path.exists():
            raise RuntimeError("Evaluation trace files exist without a manifest; refusing to overwrite or append")
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    prior_sessions = _read_jsonl(sessions_path)
    prior_turns = _read_jsonl(turns_path)
    recorded_attempts = {
        (row["session_id"], row.get("attempt", 1))
        for row in prior_sessions
        if isinstance(row.get("session_id"), str)
    }
    orphaned_turns: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for turn in prior_turns:
        session_id = turn.get("session_id")
        attempt = turn.get("attempt", 1)
        if isinstance(session_id, str) and isinstance(attempt, int):
            orphaned_turns[(session_id, attempt)].append(turn)
    for (session_id, attempt), turns in orphaned_turns.items():
        if (session_id, attempt) in recorded_attempts:
            continue
        first_turn = turns[0]
        interrupted = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "session_id": session_id,
            "attempt": attempt,
            "scenario_id": first_turn.get("scenario_id"),
            "scenario_group": first_turn.get("scenario_group"),
            "variation": first_turn.get("variation"),
            "mode": first_turn.get("mode"),
            "status": "interrupted",
            "interruption": "Turn traces were written but no session summary was committed.",
            "turns_captured": len(turns),
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        _append_jsonl(sessions_path, interrupted)
        prior_sessions.append(interrupted)
    completed_ids = {
        row["session_id"] for row in prior_sessions
        if row.get("status") == "complete" and isinstance(row.get("session_id"), str)
    }
    attempts = Counter(
        row["session_id"] for row in prior_sessions if isinstance(row.get("session_id"), str)
    )
    original_db = interaction_store.DEFAULT_DB
    original_generate = llm_client.generate_reply
    original_phrase = agent_core._phrase
    original_hybrid = os.environ.get("USE_HYBRID_RANKING")
    current_session_calls: list[dict] = []
    current_model_role = ["unknown"]
    started_run = time.monotonic()
    all_sessions = list(prior_sessions)
    new_sessions_completed = 0

    def set_model_role(role: str) -> None:
        current_model_role[0] = role

    def measured_generate(*args, **kwargs):
        started = time.monotonic()
        answer = None
        try:
            answer = original_generate(*args, **kwargs)
            return answer
        finally:
            call = {
                "role": current_model_role[0],
                "model": kwargs.get("model") or llm_client._MODEL_OVERRIDE.get() or llm_client.OLLAMA_MODEL,
                "seconds": round(time.monotonic() - started, 3),
                "responded": bool(answer),
                "failure": llm_client._MODEL_CALL_FAILURE.get(),
                "options": {
                    "seed": kwargs.get("seed", llm_client._GENERATION_SEED.get()),
                    "temperature": 0.4,
                    "max_tokens": kwargs.get("max_tokens", 160),
                    "num_ctx": kwargs.get("num_ctx"),
                    "timeout": kwargs.get("timeout"),
                    "num_thread": llm_client._GENERATION_THREADS.get(),
                },
            }
            current_session_calls.append(call)

    def measured_phrase(text, use_llm, **kwargs):
        previous_role = current_model_role[0]
        if use_llm:
            current_model_role[0] = "aurora-wording"
        try:
            answer = original_phrase(text, use_llm, **kwargs)
            if use_llm:
                phrase_decisions.append(answer != text)
            return answer
        finally:
            current_model_role[0] = previous_role

    phrase_decisions: list[bool] = []
    try:
        if local_models:
            local_model.loopback_ollama_base()
        os.environ["USE_HYBRID_RANKING"] = "false"
        llm_client.generate_reply = measured_generate
        agent_core._phrase = measured_phrase

        with tempfile.TemporaryDirectory(prefix="aurora-learning-eval-") as directory:
            interaction_store.DEFAULT_DB = Path(directory) / "synthetic-interactions.sqlite3"
            for task in tasks:
                if task.session_id in completed_ids:
                    continue
                attempt = attempts[task.session_id] + 1
                current_session_calls.clear()
                phrase_decisions.clear()
                llm_client._PHRASE_CACHE.clear()
                site_id = f"eval-{task.session_id}"
                case = replace(task.cell.case, name=task.cell.scenario_id)
                service = ConversationService(use_llm=local_models and task.mode == "local-wording")
                turn_count = len(case.messages)
                if turn_count > MAX_CUSTOMER_TURNS:
                    raise RuntimeError(
                        f"Scenario {task.cell.scenario_id} exceeds the {MAX_CUSTOMER_TURNS}-turn limit"
                    )

                def on_turn(turn: dict, _conversation, _result) -> None:
                    event = {
                        "schema_version": SCHEMA_VERSION,
                        "run_id": run_id,
                        "session_id": task.session_id,
                        "attempt": attempt,
                        "scenario_id": task.cell.scenario_id,
                        "scenario_group": task.cell.group,
                        "variation": task.variation,
                        "mode": task.mode,
                        "aurora_model": (
                            aurora_model if local_models and task.mode == "local-wording" else None
                        ),
                        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        **turn,
                    }
                    _append_jsonl(turns_path, event)

                status = "complete"
                error = None
                try:
                    if local_models and task.mode == "local-wording":
                        with llm_client.using_model(
                            aurora_model,
                            seed=_model_seed(seed, task, 0, "aurora"),
                            local_only=True,
                            num_thread=2,
                        ):
                            evaluation, _conversation = evaluate_case(
                                service,
                                case,
                                site_id=site_id,
                                phrase_decisions=phrase_decisions,
                                turn_callback=on_turn,
                                message_transform=_make_customer_transform(
                                    task=task,
                                    seed=seed,
                                    customer_model=customer_model,
                                    local_models=local_models,
                                    set_model_role=set_model_role,
                                ),
                                strict_case_assertions=not local_models,
                            )
                    else:
                        evaluation, _conversation = evaluate_case(
                            service,
                            case,
                            site_id=site_id,
                            phrase_decisions=phrase_decisions,
                            turn_callback=on_turn,
                            message_transform=_make_customer_transform(
                                task=task,
                                seed=seed,
                                customer_model=customer_model,
                                local_models=local_models,
                                set_model_role=set_model_role,
                            ),
                            strict_case_assertions=not local_models,
                        )
                    critique, critique_error = _critique(
                        evaluation["transcript"],
                        task=task,
                        seed=seed,
                        critic_model=critic_model,
                        local_models=local_models,
                        set_model_role=set_model_role,
                    )
                    if task.cell.expected_discovery_status:
                        field, expected_status = task.cell.expected_discovery_status
                        observed_status = _conversation.discovery_status.get(field)
                        if observed_status != expected_status:
                            evaluation["scenario_expectation_mismatches"].append(
                                f"expected discovery status {field}={expected_status}, got {observed_status or 'unset'}"
                            )
                            if not local_models:
                                evaluation["failures"].append(
                                    f"expected discovery status {field}={expected_status}, got {observed_status or 'unset'}"
                                )
                                evaluation["passed"] = False
                    evaluation["final_state"] = {
                        "mode": _conversation.mode,
                        "step": _conversation.step,
                        "done": _conversation.done,
                        "pending_field": _conversation.pending_field,
                        "answer_keys": sorted(_conversation.answers),
                        "discovery_status": dict(_conversation.discovery_status),
                        "review_required": _conversation.review_required,
                        "recommendation_present": _conversation.recommendation is not None,
                    }
                except Exception as exc:
                    status = "error"
                    error = {"type": type(exc).__name__, "message": str(exc)[:300]}
                    _append_jsonl(sessions_path, {
                        "schema_version": SCHEMA_VERSION,
                        "run_id": run_id,
                        "session_id": task.session_id,
                        "attempt": attempt,
                        "scenario_id": task.cell.scenario_id,
                        "scenario_group": task.cell.group,
                        "variation": task.variation,
                        "mode": task.mode,
                        "status": status,
                        "error": error,
                        "model_calls": list(current_session_calls),
                        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    })
                    raise

                session = {
                    "schema_version": SCHEMA_VERSION,
                    "run_id": run_id,
                    "session_id": task.session_id,
                    "attempt": attempt,
                    "scenario_id": task.cell.scenario_id,
                    "scenario_group": task.cell.group,
                    "variation": task.variation,
                    "variation_instruction": VARIATIONS[task.variation],
                    "mode": task.mode,
                    "status": status,
                    "expected_category": case.category,
                    "evaluation": evaluation,
                    "critique": critique,
                    "critique_error": critique_error,
                    "model_calls": list(current_session_calls),
                    "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                _append_jsonl(sessions_path, session)
                completed_ids.add(task.session_id)
                all_sessions.append(session)
                new_sessions_completed += 1
                current_model_role[0] = "unknown"
                if progress_callback is not None:
                    progress_callback(
                        len(completed_ids),
                        count,
                        time.monotonic() - started_run,
                        task,
                        evaluation,
                        critique_error,
                    )
                if (
                    max_new_sessions is not None
                    and new_sessions_completed >= max_new_sessions
                ):
                    break
    finally:
        interaction_store.DEFAULT_DB = original_db
        llm_client.generate_reply = original_generate
        agent_core._phrase = original_phrase
        if original_hybrid is None:
            os.environ.pop("USE_HYBRID_RANKING", None)
        else:
            os.environ["USE_HYBRID_RANKING"] = original_hybrid

    report = _summarize(all_sessions, run_id=run_id, seed=seed, target_count=count)
    batch_elapsed_seconds = round(time.monotonic() - started_run, 2)
    report["elapsed_seconds"] = batch_elapsed_seconds
    report["batch_completed_sessions"] = new_sessions_completed
    report["batch_seconds_per_session"] = round(
        batch_elapsed_seconds / new_sessions_completed, 2
    ) if new_sessions_completed else None
    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _write_learning_plan(output_dir / "learning_plan.md", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--count", type=int, default=500, help="Number of sessions (1-500); use 5-10 for a pilot.")
    parser.add_argument("--seed", type=int, default=20261008)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--aurora-model", default="llama3.2:latest")
    parser.add_argument("--customer-model", default="mistral:7b")
    parser.add_argument("--critic-model", default="phi4-mini:latest")
    parser.add_argument("--offline-deterministic", action="store_true", help="Disable all local model calls.")
    parser.add_argument(
        "--batch-size",
        type=int,
        help="Stop after this many new sessions so the run can be resumed in smaller chunks.",
    )
    args = parser.parse_args()
    if args.batch_size is not None and args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    run_id = args.run_id or (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    )
    output_dir = args.output_dir or (
        ROOT / "data" / "local" / "evaluations" / "aurora-learning" / run_id
    )
    started = time.monotonic()

    def report_progress(completed, target, elapsed, task, evaluation, critique_error):
        print(
            f"{completed}/{target} sessions | {elapsed / 60:.1f} min | "
            f"{task.mode} {task.cell.scenario_id} | "
            f"safety={'PASS' if evaluation['passed'] else 'FAIL'} | "
            f"critic={'valid' if critique_error is None else critique_error}",
            flush=True,
        )

    report = run_evaluation(
        output_dir=output_dir,
        run_id=run_id,
        count=args.count,
        seed=args.seed,
        aurora_model=args.aurora_model,
        customer_model=args.customer_model,
        critic_model=args.critic_model,
        local_models=not args.offline_deterministic,
        max_new_sessions=args.batch_size,
        progress_callback=report_progress,
    )
    print(
        f"{report['completed_sessions']}/{report['target_sessions']} sessions completed; "
        f"{report['passed_sessions']} passed deterministic checks; "
        f"{report['critic_valid_sessions']} valid critiques"
    )
    print(f"Local traces: {output_dir}")
    if report["completed_sessions"] < report["target_sessions"]:
        print(
            f"Batch complete ({report['batch_completed_sessions']} new sessions); "
            "resume with the same run settings to continue."
        )
    print(f"Elapsed: {(time.monotonic() - started) / 60:.1f} minutes")
    return 0 if (
        report["completed_sessions"] == report["target_sessions"]
        or args.batch_size is not None
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
