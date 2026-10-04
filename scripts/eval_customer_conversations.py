"""Evaluate synthetic customer dialogue locally; real leads are never touched.

Default: model-off, temporary SQLite, full transcripts in data/local.
--local-wording opts into an installed loopback Ollama model, serially.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import agent_core
import interaction_store
import llm_client
from conversation_service import ConversationService
from dialogue_cases import CASES


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
                conversation = agent_core.Conversation()
                transcript = []
                for message in case.messages:
                    started = time.monotonic()
                    phrase_start = len(phrase_decisions)
                    result = service.handle(conversation, message, site_id="local-evaluation")
                    transcript.append({
                        "customer": message, "reply": result.reply,
                        "category": result.category, "step": conversation.step,
                        "retrieval_mode": result.retrieval_mode,
                        "wording_changed": any(phrase_decisions[phrase_start:]),
                        "seconds": round(time.monotonic() - started, 3),
                    })
                    conversation = agent_core.Conversation.from_dict(conversation.to_dict())
                failures = []
                if result.category != case.category:
                    failures.append(f"category: expected {case.category}, got {result.category}")
                failures.extend(f"missing answer detail: {fragment}" for fragment in case.contains if fragment not in result.reply.casefold())
                if case.step is not None and conversation.step != case.step:
                    failures.append(f"step: expected {case.step}, got {conversation.step}")
                if case.answer and case.answer[1] not in conversation.answers.get(case.answer[0], "").casefold():
                    failures.append(f"missing/corrected fact: {case.answer[0]}")
                if case.category == "product-fit":
                    if conversation.recommendation:
                        failures.append("Customer recommendation is not permitted")
                    for candidate in conversation.candidates:
                        if candidate["name"].casefold() in result.reply.casefold():
                            failures.append("Internal candidate leaked in customer reply")
                if conversation.done:
                    brief = interaction_store.leads(site_id="local-evaluation")[-1]["sales_brief"]
                    if brief.get("approval") is not None or any(c["disposition"] not in {"HOLD", "REVIEW", "REJECTED"} for c in brief["candidates"]):
                        failures.append("Brief contains an automatic approval")
                reports.append({"name": case.name, "passed": not failures, "failures": failures, "transcript": transcript})
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
