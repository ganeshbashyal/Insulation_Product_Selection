"""Evaluate synthetic customer dialogue locally; real leads are never touched.

Default: model-off, temporary SQLite, full transcripts in data/local.
--local-wording opts into an installed loopback Ollama model, serially.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import agent_core
import interaction_store
import llm_client
from conversation_service import ConversationService
from dialogue_cases import CASES


def evaluate_case(
    service: ConversationService,
    case,
    *,
    site_id: str = "local-evaluation",
    phrase_decisions: list[bool] | None = None,
    turn_callback=None,
    message_transform: Callable[[int, str, list[dict]], tuple[str, dict]] | None = None,
    strict_case_assertions: bool = True,
) -> tuple[dict, agent_core.Conversation]:
    """Run and score one synthetic case against the isolated interaction store."""
    if not case.messages:
        raise ValueError("An evaluation case must include at least one customer message")

    phrase_decisions = phrase_decisions if phrase_decisions is not None else []
    conversation = agent_core.Conversation()
    transcript = []
    result = None
    hard_failures = []
    for turn_number, template in enumerate(case.messages):
        message, simulation = (
            message_transform(turn_number, template, transcript)
            if message_transform is not None
            else (template, None)
        )
        started = time.monotonic()
        phrase_start = len(phrase_decisions)
        result = service.handle(conversation, message, site_id=site_id)
        turn = {
            "turn_number": turn_number,
            "scenario_template": template,
            "customer": message,
            "customer_simulation": simulation,
            "reply": result.reply,
            "category": result.category,
            "step": conversation.step,
            "done": conversation.done,
            "retrieval_mode": result.retrieval_mode,
            "source_references": [
                line.strip() for line in result.reply.splitlines()
                if line.strip().casefold().startswith("source:")
            ],
            "human_review_required": result.human_review_required,
            "review_labels": list(result.review_labels),
            "wording_changed": any(phrase_decisions[phrase_start:]),
            "seconds": round(time.monotonic() - started, 3),
            "state": {
                "mode": conversation.mode,
                "pending_field": conversation.pending_field,
                "answer_keys": sorted(conversation.answers),
                "discovery_status": dict(conversation.discovery_status),
                "candidate_count": len(conversation.candidates),
            },
        }
        transcript.append(turn)
        if conversation.recommendation:
            hard_failures.append("Customer recommendation is not permitted")
        for candidate in conversation.candidates:
            name = candidate.get("name")
            if isinstance(name, str) and name and name.casefold() in result.reply.casefold():
                hard_failures.append("Internal candidate leaked in customer reply")
        if turn_callback is not None:
            turn_callback(turn, conversation, result)
        conversation = agent_core.Conversation.from_dict(conversation.to_dict())

    failures = hard_failures
    expectation_mismatches = []
    if result.category != case.category:
        expectation_mismatches.append(f"category: expected {case.category}, got {result.category}")
    expectation_mismatches.extend(
        f"missing answer detail: {fragment}"
        for fragment in case.contains
        if fragment not in result.reply.casefold()
    )
    if case.step is not None and conversation.step != case.step:
        expectation_mismatches.append(f"step: expected {case.step}, got {conversation.step}")
    if case.answer and case.answer[1] not in conversation.answers.get(case.answer[0], "").casefold():
        expectation_mismatches.append(f"missing/corrected fact: {case.answer[0]}")
    seen_replies = set()
    for index, turn in enumerate(transcript):
        reply = turn["reply"]
        normalized_reply = " ".join(reply.casefold().split())
        if "?" in reply and normalized_reply in seen_replies:
            previous_state = transcript[index - 1]["state"] if index else {}
            current_state = turn["state"]
            field = previous_state.get("pending_field")
            previous_status = previous_state.get("discovery_status", {}).get(field)
            current_status = current_state.get("discovery_status", {}).get(field)
            if (
                field
                and current_state.get("pending_field") == field
                and previous_status in {"provided", "unknown", "skipped"}
                and current_status == previous_status
            ):
                hard_failures.append("repeated assistant question after a resolved answer")
        if "?" in reply:
            seen_replies.add(normalized_reply)
        if re.search(r"\b(?:i've noted|i have noted|i've also noted)\b", reply, re.I):
            hard_failures.append("stock acknowledgement makes discovery feel repetitive")
        if turn["category"] == "product-fit" and reply.count("?") > 1:
            hard_failures.append("multiple questions in one discovery reply")
    if conversation.done:
        brief = interaction_store.leads(site_id=site_id)[-1]["sales_brief"]
        if brief.get("approval") is not None or any(
            candidate["disposition"] not in {"HOLD", "REVIEW", "REJECTED"}
            for candidate in brief["candidates"]
        ):
            hard_failures.append("Brief contains an automatic approval")
    if strict_case_assertions:
        failures.extend(expectation_mismatches)
    return {
        "name": case.name,
        "passed": not failures,
        "failures": failures,
        "scenario_expectation_mismatches": expectation_mismatches,
        "scenario_expectations_passed": not expectation_mismatches,
        "transcript": transcript,
    }, conversation


def evaluate(*, local_wording: bool = False, names: list[str] | None = None) -> dict:
    cases = [case for case in CASES if not names or case.name in names]
    if names and set(names) - {case.name for case in CASES}:
        raise ValueError("Unknown scenario name")
    if local_wording:
        host = urlparse(llm_client.OLLAMA_HOST)
        if host.scheme != "http" or host.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Local wording evaluation requires a loopback Ollama host")
        if not llm_client.ollama_available():
            raise RuntimeError("Local Ollama is unavailable; no model was downloaded")

    reports = []
    model_calls = []
    phrase_decisions = []
    original_generate = llm_client.generate_reply
    original_phrase = agent_core._phrase
    original_db = interaction_store.DEFAULT_DB
    original_hybrid = os.environ.get("USE_HYBRID_RANKING")

    def measured_generate(*args, **kwargs):
        started = time.monotonic()
        answer = original_generate(*args, **kwargs)
        model_calls.append({"seconds": round(time.monotonic() - started, 3), "responded": bool(answer)})
        return answer

    def measured_phrase(text, use_llm, **kwargs):
        answer = original_phrase(text, use_llm, **kwargs)
        if use_llm:
            phrase_decisions.append(answer != text)
        return answer

    try:
        os.environ["USE_HYBRID_RANKING"] = "false"
        llm_client.generate_reply = measured_generate
        agent_core._phrase = measured_phrase
        llm_client._PHRASE_CACHE.clear()
        with tempfile.TemporaryDirectory(prefix="aurora-dialogue-") as directory:
            interaction_store.DEFAULT_DB = Path(directory) / "synthetic.sqlite3"
            service = ConversationService(use_llm=local_wording)
            for case in cases:
                report, _ = evaluate_case(
                    service, case, phrase_decisions=phrase_decisions,
                )
                reports.append(report)
    finally:
        interaction_store.DEFAULT_DB = original_db
        llm_client.generate_reply = original_generate
        agent_core._phrase = original_phrase
        if original_hybrid is None:
            os.environ.pop("USE_HYBRID_RANKING", None)
        else:
            os.environ["USE_HYBRID_RANKING"] = original_hybrid

    return {
        "mode": "local-wording" if local_wording else "model-off",
        "model": llm_client.OLLAMA_MODEL if local_wording else None,
        "cases": len(reports), "passed": sum(row["passed"] for row in reports),
        "model_calls": model_calls,
        "note": "Inspect full transcripts for relevance and naturalness. Passing assertions/citations alone does not prove answer quality.",
        "scenarios": reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-wording", action="store_true")
    parser.add_argument("--case", action="append", dest="names")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "local" / "conversation_eval_report.json")
    args = parser.parse_args()
    report = evaluate(local_wording=args.local_wording, names=args.names)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report['passed']}/{report['cases']} scenarios passed ({report['mode']}); {len(report['model_calls'])} local model calls")
    print(f"Full transcripts: {args.output}")
    return 0 if report["passed"] == report["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
