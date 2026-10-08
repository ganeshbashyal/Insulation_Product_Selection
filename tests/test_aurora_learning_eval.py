import json

import pytest

import interaction_store
import llm_client
from dialogue_cases import CASES
from scripts import aurora_learning_eval


def test_scenario_matrix_is_50_cells_and_500_balanced_sessions():
    cells = aurora_learning_eval.scenario_cells()
    tasks = aurora_learning_eval.evaluation_tasks(seed=19)

    assert len(cells) == 50
    assert len(tasks) == 500
    assert len({task.session_id for task in tasks}) == 500
    assert sum(task.mode == "model-off" for task in tasks) == 250
    assert sum(task.mode == "local-wording" for task in tasks) == 250
    assert len({task.cell.group for task in tasks}) == 10
    assert aurora_learning_eval.evaluation_tasks(seed=19) == tasks


def test_customer_message_guard_rejects_invented_details():
    assert aurora_learning_eval._safe_customer_message(
        "My wall is cold and it is 50 metres long.", "My wall is cold"
    ) == ("My wall is cold", "model introduced a number not present in the scenario")
    assert aurora_learning_eval._safe_customer_message(
        "Call me at 0400 123 456.", "Please contact the team"
    ) == ("Please contact the team", "model introduced contact information")
    assert aurora_learning_eval._safe_customer_message(
        "My wall feels cold.", "My wall is cold"
    ) == ("My wall feels cold.", None)


def test_critic_output_requires_valid_rubric_scores():
    valid = json.dumps({
        "scores": {
            "relevance": 4, "continuity": 4, "naturalness": 3,
            "evidence_care": 5, "consent_and_review": 5,
        },
        "issues": ["A short observation."],
        "summary": "An advisory summary.",
    })
    critique, error = aurora_learning_eval._parse_critique(valid)
    assert error is None
    assert critique["scores"]["evidence_care"] == 5
    flat_scores = json.dumps({
        "relevance": 4, "continuity": 4, "naturalness": 4,
        "evidence_care": 5, "consent_and_review": 5,
    })
    assert aurora_learning_eval._parse_critique(flat_scores)[1] is None
    assert aurora_learning_eval._parse_critique('{"scores":{"relevance":9}}')[1] == "invalid_score:relevance"


def test_critic_retries_once_when_local_model_breaks_rubric(monkeypatch):
    case = next(case for case in CASES if case.name == "greet-then-select")
    cell = next(cell for cell in aurora_learning_eval.scenario_cells() if cell.case.name == case.name)
    task = aurora_learning_eval.EvaluationTask(cell, 0, "model-off", "critic-retry")
    outputs = iter((
        '{"scores":{"relevance":0}}',
        json.dumps({
            "scores": {
                "relevance": 4, "continuity": 4, "naturalness": 4,
                "evidence_care": 5, "consent_and_review": 5,
            },
            "issues": [],
            "summary": "The exchange is clear.",
        }),
    ))
    prompts = []

    def fake_generate(_system, prompt, **_kwargs):
        prompts.append(prompt)
        return next(outputs)

    monkeypatch.setattr(llm_client, "generate_reply", fake_generate)
    monkeypatch.setattr(aurora_learning_eval.local_model, "chat_models", lambda: ["phi4-mini:latest"])
    critique, error = aurora_learning_eval._critique(
        [{"customer": "Hi", "reply": "Hello.", "category": "greeting",
          "retrieval_mode": "none", "human_review_required": False}],
        task=task,
        seed=11,
        critic_model="phi4-mini:latest",
        local_models=True,
        set_model_role=lambda _role: None,
    )

    assert error is None
    assert critique["retry_count"] == 1
    assert len(prompts) == 2
    assert "Return valid JSON only" in prompts[1]


def test_jsonl_reader_recovers_incomplete_final_record(tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_bytes(b'{"session_id":"complete"}\n{"session_id":')

    assert aurora_learning_eval._read_jsonl(path) == [{"session_id": "complete"}]
    assert path.read_bytes() == b'{"session_id":"complete"}\n'


def test_offline_run_captures_traces_and_flags_unknown_answer(tmp_path, monkeypatch):
    cells = {cell.case.name: cell for cell in aurora_learning_eval.scenario_cells()}
    tasks = [
        aurora_learning_eval.EvaluationTask(
            cells[name], index, "model-off", f"session-{name}"
        )
        for index, name in enumerate(("skip-project-stage", "unknown-project-stage"))
    ]
    monkeypatch.setattr(aurora_learning_eval, "evaluation_tasks", lambda **_kwargs: tasks)
    original_db = interaction_store.DEFAULT_DB
    output = tmp_path / "run"

    report = aurora_learning_eval.run_evaluation(
        output_dir=output,
        run_id="offline-unit",
        count=2,
        seed=23,
        local_models=False,
        require_git_ignored=False,
        max_new_sessions=1,
    )

    assert report["completed_sessions"] == 1
    assert report["batch_completed_sessions"] == 1
    assert report["batch_seconds_per_session"] is not None
    assert report["passed_sessions"] == 1
    assert report["deterministic_failures"] == {}
    assert interaction_store.DEFAULT_DB == original_db
    turns = [json.loads(line) for line in (output / "turns.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(turns) == 2
    assert all(turn["customer"] for turn in turns)
    sessions = [json.loads(line) for line in (output / "sessions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(sessions) == 1
    assert (output / "learning_plan.md").is_file()

    resumed = aurora_learning_eval.run_evaluation(
        output_dir=output,
        run_id="offline-unit",
        count=2,
        seed=23,
        local_models=False,
        require_git_ignored=False,
        max_new_sessions=1,
    )
    assert resumed["completed_sessions"] == 2
    assert resumed["batch_completed_sessions"] == 1
    assert resumed["batch_seconds_per_session"] is not None
    assert len((output / "sessions.jsonl").read_text(encoding="utf-8").splitlines()) == 2
    assert len((output / "turns.jsonl").read_text(encoding="utf-8").splitlines()) == 4

    def unexpected_service(*_args, **_kwargs):
        pytest.fail("A completed run must not rerun sessions when resumed")

    monkeypatch.setattr(aurora_learning_eval, "ConversationService", unexpected_service)
    completed = aurora_learning_eval.run_evaluation(
        output_dir=output,
        run_id="offline-unit",
        count=2,
        seed=23,
        local_models=False,
        require_git_ignored=False,
    )
    assert completed["completed_sessions"] == 2
    assert len((output / "sessions.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_resume_marks_orphan_turns_as_interrupted_and_uses_new_attempt(tmp_path, monkeypatch):
    output = tmp_path / "interrupted"
    output.mkdir()
    task = aurora_learning_eval.evaluation_tasks(seed=41, count=1)[0]
    task = aurora_learning_eval.replace(task, mode="model-off")
    monkeypatch.setattr(aurora_learning_eval, "evaluation_tasks", lambda **_kwargs: [task])
    (output / "manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "run_id": "interrupted-run",
        "seed": 41,
        "target_sessions": 1,
        "scenario_cells": 50,
        "variations_per_cell": 10,
        "models": {"aurora": None, "customer_simulator": None, "critic": None},
    }), encoding="utf-8")
    (output / "turns.jsonl").write_text(json.dumps({
        "schema_version": 1,
        "run_id": "interrupted-run",
        "session_id": task.session_id,
        "attempt": 1,
        "scenario_id": task.cell.scenario_id,
        "scenario_group": task.cell.group,
        "variation": task.variation,
        "mode": task.mode,
        "turn_number": 0,
        "customer": "Synthetic customer input.",
        "reply": "Synthetic Aurora reply.",
    }) + "\n", encoding="utf-8")

    report = aurora_learning_eval.run_evaluation(
        output_dir=output,
        run_id="interrupted-run",
        count=1,
        seed=41,
        local_models=False,
        require_git_ignored=False,
    )

    sessions = [
        json.loads(line) for line in (output / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["status"] for row in sessions] == ["interrupted", "complete"]
    assert [row["attempt"] for row in sessions] == [1, 2]
    assert report["completed_sessions"] == 1
    assert report["incomplete_attempts"] == 1


def test_local_run_uses_only_selected_models_and_redacts_critic_input(tmp_path, monkeypatch):
    case = next(case for case in CASES if case.name == "greet-then-select")
    cell = next(
        cell for cell in aurora_learning_eval.scenario_cells()
        if cell.case.name == case.name
    )
    task = aurora_learning_eval.EvaluationTask(cell, 1, "local-wording", "model-session")
    monkeypatch.setattr(aurora_learning_eval, "evaluation_tasks", lambda **_kwargs: [task])
    monkeypatch.setattr(aurora_learning_eval.local_model, "chat_models", lambda: [
        "llama3.2:latest", "mistral:7b", "phi4-mini:latest",
    ])
    monkeypatch.setattr(aurora_learning_eval.local_model, "loopback_ollama_base", lambda: "http://127.0.0.1:11434")
    calls = []

    def fake_generate(system_prompt, user_prompt, **kwargs):
        calls.append({
            "system": system_prompt,
            "prompt": user_prompt,
            "seed": kwargs.get("seed", llm_client._GENERATION_SEED.get()),
            "num_thread": kwargs.get("num_thread", llm_client._GENERATION_THREADS.get()),
            **kwargs,
        })
        if "You are a critic" in system_prompt:
            return json.dumps({
                "scores": {
                    "relevance": 4, "continuity": 4, "naturalness": 4,
                    "evidence_care": 5, "consent_and_review": 5,
                },
                "issues": [],
                "summary": "Suitable synthetic test exchange.",
            })
        if "fictional insulation customer" in system_prompt:
            source = json.loads(user_prompt)["customer_message_to_rephrase"]
            return source
        return "Please tell me more about the project."

    monkeypatch.setattr(llm_client, "generate_reply", fake_generate)
    output = tmp_path / "local-model-run"
    report = aurora_learning_eval.run_evaluation(
        output_dir=output,
        run_id="local-model-unit",
        count=1,
        seed=31,
        local_models=True,
        require_git_ignored=False,
    )

    assert report["completed_sessions"] == 1
    assert report["critic_valid_sessions"] == 1
    assert {call["model"] for call in calls} == {"llama3.2:latest", "mistral:7b", "phi4-mini:latest"}
    assert all(isinstance(call["seed"], int) and call["seed"] >= 0 for call in calls)
    assert all(call["num_thread"] == 2 for call in calls)
    assert "synthetic@example.com" not in aurora_learning_eval._redact_for_critic(
        "Please contact synthetic@example.com or 0400 123 456."
    )
    session = json.loads((output / "sessions.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert session["model_calls"]
    assert {call["role"] for call in session["model_calls"]} >= {"customer-simulator", "transcript-critic"}
