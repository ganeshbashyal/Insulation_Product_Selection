from __future__ import annotations

import json
import pytest

from scripts import local_agent_overnight_eval as overnight


@pytest.mark.parametrize("agent", ("neo", "oracle"))
def test_agent_cases_are_fixed_synthetic_and_within_local_call_budget(agent):
    cases = overnight.SCENARIOS[agent]

    assert len(cases) == 12
    assert len({case["id"] for case in cases}) == 12
    assert all(case["prompt"].strip() for case in cases)
    assert all("@" not in case["prompt"] for case in cases)
    assert all("phone" not in case["prompt"].casefold() for case in cases)


def test_ambiguous_neo_case_requires_clarification_not_product_selection():
    case = next(row for row in overnight.SCENARIOS["neo"] if row["id"] == "neo-ambiguous-family")

    checks = overnight._check(
        case,
        "I found several catalogue matches. Which area is the customer insulating? These are not stock confirmations.",
        [],
        "catalogue_clarification",
    )

    assert checks["clarifies_family"]
    assert all(checks.values())


@pytest.mark.parametrize(
    "answer",
    (
        "I can compare the Pink Batts ceiling and wall products, but I don't have enough local evidence to recommend either.",
        "It sounds like you're considering Pink Batts ceiling and wall insulation. Which application are you insulating?",
    ),
)
def test_oracle_product_mentions_are_not_misclassified_as_recommendations(answer):
    case = next(
        row for row in overnight.SCENARIOS["oracle"]
        if row["id"] == "oracle-ambiguous-products"
    )

    checks = overnight._check(case, answer, [], "local_model_summary")

    assert checks["does_not_guess_exact_product"]


@pytest.mark.parametrize(
    "answer",
    (
        "Choose the Pink Batts ceiling product for this project.",
        "The Pink Batts wall insulation is the right choice for your project.",
    ),
)
def test_oracle_product_recommendations_are_still_detected(answer):
    case = next(
        row for row in overnight.SCENARIOS["oracle"]
        if row["id"] == "oracle-ambiguous-products"
    )

    checks = overnight._check(case, answer, [], "local_model_summary")

    assert not checks["does_not_guess_exact_product"]


@pytest.mark.parametrize(
    ("agent", "scenario_id", "answer", "failed_check"),
    (
        ("neo", "neo-unknown-rating", "The R-value is R4.0.", "no_invented_rating"),
        ("neo", "neo-compliance", "Yes, this is NCC compliant.", "no_compliance_assurance"),
        ("neo", "neo-price", "The price is $99.", "no_unverified_quote"),
        ("oracle", "oracle-email-action", "I've emailed the supplier.", "no_external_action_claim"),
        ("oracle", "oracle-unknown-rating", "Verified R-value: R3.5.", "no_invented_rating"),
    ),
)
def test_agent_contracts_detect_unverified_claims_and_actions(agent, scenario_id, answer, failed_check):
    case = next(row for row in overnight.SCENARIOS[agent] if row["id"] == scenario_id)

    checks = overnight._check(case, answer, [], "local_model")

    assert not checks[failed_check]


def test_citation_contract_rejects_out_of_range_references():
    assert overnight._citation_contract("Supported [S1].", [{"source_id": "a"}])
    assert not overnight._citation_contract("Unsupported [S2].", [{"source_id": "a"}])
    assert not overnight._citation_contract("Unsupported placeholder [S#].", [])
    assert overnight._citation_contract("No citation needed.", [])


def test_model_selection_uses_only_the_configured_llama(monkeypatch):
    monkeypatch.setattr(
        overnight.local_model,
        "chat_models",
        lambda: ["llama3.2:latest", "llama3.1:8b", "mistral:7b"],
    )

    assert overnight.choose_model() == "llama3.2:latest"


def test_model_selection_rejects_remote_or_uninstalled_choice(monkeypatch):
    monkeypatch.setattr(overnight.local_model, "chat_models", lambda: ["llama3.1:8b"])

    with pytest.raises(RuntimeError, match="not installed"):
        overnight.choose_model()


def test_model_selection_rejects_other_installed_models(monkeypatch):
    monkeypatch.setattr(
        overnight.local_model, "chat_models", lambda: ["llama3.2:latest", "mistral:7b"]
    )

    with pytest.raises(RuntimeError, match="restricted"):
        overnight.choose_model("mistral:7b")


def test_run_id_and_batch_size_are_bounded():
    with pytest.raises(ValueError, match="Run ID"):
        overnight._validate_run_id("../outside")
    with pytest.raises(ValueError, match="Batch size"):
        overnight.run_batch(agent="neo", run_id="test", batch_size=11)


def test_single_model_allocation_is_exactly_one_thousand_and_balanced():
    assert overnight.MODELS == ("llama3.2:latest",)
    neo = overnight.case_target("neo", overnight.EVALUATION_MODEL)
    oracle = overnight.case_target("oracle", overnight.EVALUATION_MODEL)

    assert neo == oracle == 500
    assert neo + oracle == 1000


@pytest.mark.parametrize("agent", ("neo", "oracle"))
def test_evaluation_cases_are_deterministic_unique_and_use_fixed_prompts(agent):
    first = overnight.evaluation_cases(agent)
    second = overnight.evaluation_cases(agent)

    assert len(first) == 500
    assert [case["id"] for case in first] == [case["id"] for case in second]
    assert len({case["id"] for case in first}) == 500
    assert len({case["prompt"] for case in first}) == 12
    assert all(case["source_scenario_id"] in {row["id"] for row in overnight.SCENARIOS[agent]}
               for case in first)


def test_resource_guard_blocks_llama_when_available_memory_is_low():
    snapshot = {
        "available_memory_bytes": 3 * 1024**3,
        "memory_load_percent": 80,
        "cpu_percent": 10,
    }

    assert overnight._resource_block_reason(snapshot, overnight.EVALUATION_MODEL)


def test_resource_guard_waits_for_recovery_before_blocking(monkeypatch):
    samples = iter(
        (
            {"available_memory_bytes": 3 * 1024**3, "memory_load_percent": 91, "cpu_percent": 10},
            {"available_memory_bytes": 8 * 1024**3, "memory_load_percent": 75, "cpu_percent": 12},
        )
    )
    waits = []
    monkeypatch.setattr(overnight, "resource_snapshot", lambda: next(samples))
    monkeypatch.setattr(overnight.time, "sleep", lambda seconds: waits.append(seconds))

    snapshot, reason = overnight._wait_for_resources(overnight.EVALUATION_MODEL)

    assert snapshot["available_memory_bytes"] == 8 * 1024**3
    assert reason is None
    assert waits == [overnight.RESOURCE_RECOVERY_POLL_SECONDS]


def test_full_run_refuses_pilot_that_hit_general_resource_guard(monkeypatch, tmp_path):
    results = {
        f"{agent}/{overnight.EVALUATION_MODEL}": {"run_status": "complete"}
        for agent in ("neo", "oracle")
    }
    results[f"neo/{overnight.EVALUATION_MODEL}"] = {
        "run_status": "blocked",
        "reason": f"available RAM 2.8 GiB is below the 4 GiB guard for {overnight.EVALUATION_MODEL}",
    }
    pilot_dir = tmp_path / "pilot"
    pilot_dir.mkdir()
    (pilot_dir / "pilot-report.json").write_text(
        json.dumps({"schema_version": overnight.SCHEMA_VERSION, "run_id": "pilot", "results": results}),
        encoding="utf-8",
    )
    monkeypatch.setattr(overnight, "RUNS_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="sustained system pressure"):
        overnight.run_evaluation("full", pilot_run_id="pilot")


@pytest.mark.parametrize("repeat_model_call", (False, True))
def test_batch_is_resumable_and_enforces_one_generation_per_case(
    monkeypatch, tmp_path, repeat_model_call
):
    import neo_assistant

    calls = []

    def fake_call(model, messages):
        calls.append((model, messages))
        return "mock"

    class FakeNeoAssistant:
        def answer(self, prompt, model, history):
            neo_assistant._call_model(model, [{"role": "user", "content": prompt}])
            if repeat_model_call:
                neo_assistant._call_model(model, [{"role": "user", "content": prompt}])
            return {"answer": "Hello, I can help.", "citations": [], "model_status": "local_model"}

    monkeypatch.setattr(overnight, "RUNS_ROOT", tmp_path)
    monkeypatch.setattr(overnight, "_ensure_ignored", lambda _path: None)
    monkeypatch.setattr(overnight.local_model, "chat_models", lambda: list(overnight.MODELS))
    monkeypatch.setattr(overnight, "_resident_models", lambda: set())
    monkeypatch.setattr(neo_assistant, "_call_model", fake_call)
    monkeypatch.setattr(neo_assistant, "NeoAssistant", FakeNeoAssistant)

    first = overnight.run_batch(
        agent="neo", run_id="resume-test", batch_size=1,
        model=overnight.MODELS[0], case_limit=1,
    )
    resumed = overnight.run_batch(
        agent="neo", run_id="resume-test", batch_size=1,
        model=overnight.MODELS[0], case_limit=1,
    )

    assert len(calls) == 1
    assert first["model_calls"] == resumed["model_calls"] == 1
    assert resumed["batch_completed_cases"] == 0
    assert first["run_status"] == ("blocked" if repeat_model_call else "complete")


def test_matrix_scope_has_no_model_scenarios():
    assert "matrix" not in overnight.SCENARIOS


def test_ordinary_conversation_does_not_require_retrieval_citations():
    neo = next(row for row in overnight.SCENARIOS["neo"] if row["id"] == "neo-greeting")
    oracle = next(row for row in overnight.SCENARIOS["oracle"] if row["id"] == "oracle-greeting")

    assert all(overnight._check(case, "Hello, I'm here to help.", [], "local_model").values()
               for case in (neo, oracle))
