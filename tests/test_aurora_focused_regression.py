import json
from types import SimpleNamespace

import pytest

import agent_core
import llm_client
from scripts import aurora_focused_regression as focused


def test_focus_matrix_contains_balanced_sessions():
    tasks = focused.evaluation_tasks(seed=7)

    assert len(tasks) == focused.MAX_CASES == 48
    assert len({task["session_id"] for task in tasks}) == focused.MAX_CASES
    assert {scenario["id"] for scenario in (task["scenario"] for task in tasks)} == {
        "r-value",
        "thermal-bridging",
        "sarking",
        "thanks-standalone",
        "thanks-during-discovery",
        "thanks-courtesy-control",
    }
    assert focused.evaluation_tasks(seed=7) == tasks
    with pytest.raises(ValueError):
        focused.evaluation_tasks(seed=7, count=focused.MAX_CASES + 1)


@pytest.mark.parametrize(
    ("scenario_id", "candidate"),
    (
        ("r-value", "Could you explain what R-value means?"),
        ("thermal-bridging", "What does thermal bridging mean?"),
        ("sarking", "Could you explain sarking under a roof?"),
        ("thanks-standalone", "Thanks, that's all I needed. I'm done for now."),
        ("thanks-during-discovery", "I appreciate that; that's everything for now."),
        ("thanks-courtesy-control", "Thanks for your help."),
    ),
)
def test_generated_input_must_preserve_topic_and_intent(scenario_id, candidate):
    scenario = next(row for row in focused.SCENARIOS if row["id"] == scenario_id)

    assert focused._preserves_intent(candidate, scenario)


@pytest.mark.parametrize(
    ("scenario_id", "candidate"),
    (
        ("r-value", "Could you explain insulation?"),
        ("thermal-bridging", "What does insulation mean?"),
        ("sarking", "Could you explain roofing?"),
        ("thanks-standalone", "Thanks for your help."),
        ("thanks-during-discovery", "I appreciate the explanation."),
        ("thanks-courtesy-control", "That's all, thank you."),
    ),
)
def test_generated_input_rejects_lost_topic_or_closure(scenario_id, candidate):
    scenario = next(row for row in focused.SCENARIOS if row["id"] == scenario_id)

    assert not focused._preserves_intent(candidate, scenario)


def test_unsafe_generated_input_falls_back_to_fixed_phrase(monkeypatch):
    task = next(
        task for task in focused.evaluation_tasks(seed=3)
        if task["scenario"]["id"] == "r-value"
    )
    monkeypatch.setattr(
        focused.llm_client,
        "generate_reply",
        lambda *_args, **_kwargs: "What is the R-value for a 90mm wall?",
    )

    result = focused._make_paraphrase(task, seed=3, model=focused.MODEL)

    assert result["status"] == "template_fallback"
    assert result["message"] == task["scenario"]["prompt"]
    assert "number" in result["reason"]


def test_concept_contract_requires_direct_cited_grounded_answer():
    scenario = next(row for row in focused.SCENARIOS if row["id"] == "r-value")
    task = {"scenario": scenario}
    conversation = agent_core.Conversation()
    result = SimpleNamespace(
        reply=(
            "R-Value: Thermal resistance. Higher = better insulation.\n"
            "Source: knowledge/industry/training/01_glossary.md, R-Value."
        ),
        category="informational",
        retrieval_mode="local-glossary",
    )

    evaluation = focused._check_response(task, result, conversation, None)

    assert evaluation["passed"]


def test_concept_contract_flags_product_evidence_deflection():
    scenario = next(row for row in focused.SCENARIOS if row["id"] == "r-value")
    result = SimpleNamespace(
        reply="Which product do you mean? Please share its name so I can check the right local evidence.",
        category="informational",
        retrieval_mode="product-evidence",
    )

    evaluation = focused._check_response(
        {"scenario": scenario},
        result,
        agent_core.Conversation(),
        None,
    )

    assert not evaluation["passed"]
    assert "local_glossary_retrieval" in evaluation["failures"]
    assert "source_citation" in evaluation["failures"]
    assert "answer_is_direct" in evaluation["failures"]


def test_concept_contract_flags_unrequested_product_catalogue_answer():
    scenario = next(row for row in focused.SCENARIOS if row["id"] == "sarking")
    result = SimpleNamespace(
        reply=(
            "Polyester Solutions Under Floor Rolls - PolyFB: Batt insulation product.\n"
            "Source: local families.json."
        ),
        category="informational",
        retrieval_mode="product-evidence",
    )

    evaluation = focused._check_response(
        {"scenario": scenario},
        result,
        agent_core.Conversation(),
        None,
    )

    assert not evaluation["passed"]
    assert "no_unrequested_product_answer" in evaluation["failures"]


def test_closure_contract_requires_no_restart_and_preserved_discovery():
    scenario = next(row for row in focused.SCENARIOS if row["id"] == "thanks-during-discovery")
    conversation = agent_core.Conversation(
        mode="discovery",
        step=1,
        pending_field="application",
        answers={"problem": "My external wall is cold"},
    )
    before = {
        "answers": dict(conversation.answers),
        "pending_field": conversation.pending_field,
        "discovery_status": dict(conversation.discovery_status),
        "lead": dict(conversation.lead),
    }
    result = SimpleNamespace(
        reply="You're welcome. We can pick this up whenever you need.",
        category="greeting",
        retrieval_mode="none",
    )

    assert focused._check_response(
        {"scenario": scenario},
        result,
        conversation,
        before,
    )["passed"]

    conversation.answers["priority"] = "all done"
    failing = focused._check_response(
        {"scenario": scenario},
        SimpleNamespace(
            reply="Where is the insulation needed?",
            category="product-fit",
            retrieval_mode="needs-capture",
        ),
        conversation,
        before,
    )
    assert not failing["passed"]
    assert "closure_route" in failing["failures"]
    assert "no_new_intake_prompt" in failing["failures"]
    assert "discovery_facts_preserved" in failing["failures"]


def test_run_is_resumable_and_isolates_local_stores(tmp_path, monkeypatch):
    task = focused.evaluation_tasks(seed=13, count=1)[0]
    task["scenario"] = next(row for row in focused.SCENARIOS if row["id"] == "r-value")
    monkeypatch.setattr(focused, "evaluation_tasks", lambda **_kwargs: [task])
    monkeypatch.setattr(focused.local_model, "loopback_ollama_base", lambda: "http://127.0.0.1:11434")
    monkeypatch.setattr(focused.local_model, "chat_models", lambda: [focused.MODEL])
    original_interaction = focused.interaction_store.DEFAULT_DB
    original_research = focused.research_store.DEFAULT_DB

    class FakeConversation:
        def __init__(self):
            self.answers = {}
            self.pending_field = None
            self.mode = "enquiry"
            self.discovery_status = {}
            self.lead = {}
            self.done = False
            self.recommendation = None

        def to_dict(self):
            return {"answers": self.answers, "pending_field": self.pending_field}

        @classmethod
        def from_dict(cls, value):
            result = cls()
            result.answers = dict(value["answers"])
            result.pending_field = value["pending_field"]
            return result

    class FakeService:
        def __init__(self, **_kwargs):
            pass

        def handle(self, conversation, _message, **_kwargs):
            return SimpleNamespace(
                reply=(
                    "R-Value: Thermal resistance. Higher = better insulation.\n"
                    "Source: knowledge/industry/training/01_glossary.md, R-Value."
                ),
                category="informational",
                retrieval_mode="local-glossary",
                human_review_required=False,
                review_labels=(),
            )

    monkeypatch.setattr(focused.agent_core, "Conversation", FakeConversation)
    monkeypatch.setattr(focused, "ConversationService", FakeService)

    def fake_generate(_system, prompt, **_kwargs):
        if prompt.startswith("Rewrite this synthetic"):
            return task["scenario"]["prompt"]
        pytest.fail("Unexpected model call in local regression unit test")

    monkeypatch.setattr(focused.llm_client, "generate_reply", fake_generate)
    output = tmp_path / "regression"
    first = focused.run_evaluation(
        output_dir=output,
        run_id="focused-unit",
        count=1,
        batch_size=1,
        seed=13,
        require_git_ignored=False,
    )

    assert first["completed_sessions"] == 1
    assert first["passed_sessions"] == 1
    assert focused.interaction_store.DEFAULT_DB == original_interaction
    assert focused.research_store.DEFAULT_DB == original_research
    rows = [json.loads(line) for line in (output / "sessions.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["paraphrase"]["status"] == "generated"
    assert rows[0]["transcript"][0]["message"] == task["scenario"]["prompt"]

    def unexpected_service(**_kwargs):
        pytest.fail("A completed session must not run again when resumed")

    monkeypatch.setattr(focused, "ConversationService", unexpected_service)
    resumed = focused.run_evaluation(
        output_dir=output,
        run_id="focused-unit",
        count=1,
        batch_size=1,
        seed=13,
        require_git_ignored=False,
    )
    assert resumed["completed_sessions"] == 1
    assert resumed["batch_completed_sessions"] == 0
    assert len((output / "sessions.jsonl").read_text().splitlines()) == 1


def test_non_loopback_ollama_host_is_rejected_before_discovery(tmp_path, monkeypatch):
    monkeypatch.setattr(focused.local_model, "loopback_ollama_base", lambda: "http://192.0.2.10:11434")
    monkeypatch.setattr(
        focused.local_model,
        "chat_models",
        lambda: pytest.fail("Model discovery must not run for a non-loopback endpoint"),
    )

    with pytest.raises(RuntimeError, match="loopback-only"):
        focused.run_evaluation(
            output_dir=tmp_path / "remote",
            run_id="remote-refused",
            count=1,
            batch_size=1,
            require_git_ignored=False,
        )
