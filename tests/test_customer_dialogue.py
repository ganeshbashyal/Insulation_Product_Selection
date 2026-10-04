"""Customer-facing contracts, not just classifier-label checks."""
import pytest
import urllib.request

import agent_core
import interaction_store
import llm_client
import research_store
from conversation_service import ConversationService
from dialogue_cases import CASES
from router import MessageRouter


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_customer_conversation(case, tmp_path, monkeypatch):
    monkeypatch.setattr(interaction_store, "DEFAULT_DB", tmp_path / "interactions.sqlite3")
    monkeypatch.setattr(research_store, "DEFAULT_DB", tmp_path / "absent-research.sqlite3")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("Model-off conversations must not use a network"))
    service = ConversationService(use_llm=False, router=MessageRouter(use_llm=False))
    conversation = agent_core.Conversation()
    for message in case.messages:
        result = service.handle(conversation, message, site_id="local")
        conversation = agent_core.Conversation.from_dict(conversation.to_dict())
    assert result.category == case.category
    for fragment in case.contains:
        assert fragment in result.reply.casefold()
    if case.step is not None:
        assert conversation.step == case.step
    if case.answer:
        key, fragment = case.answer
        assert fragment in conversation.answers[key].casefold()


@pytest.fixture
def local_service(tmp_path, monkeypatch):
    monkeypatch.setattr(interaction_store, "DEFAULT_DB", tmp_path / "interactions.sqlite3")
    monkeypatch.setattr(research_store, "DEFAULT_DB", tmp_path / "absent-research.sqlite3")
    return ConversationService(use_llm=False)


def test_question_during_contact_does_not_capture_consent_and_removes_legacy_recommendation(local_service):
    family = next(row for row in agent_core.FAMILIES if row["family_id"] == "THERMOTEC_NUWRAP_5")
    conversation = agent_core.Conversation(
        step=len(agent_core.QUESTIONS), mode="selection",
        answers={"problem": "noisy waste pipe"},
        recommendation={key: family[key] for key in ("family_id", "name", "manufacturer")},
        lead={"customer_name": "Jane"},
    )
    local_service.handle(conversation, "What is R-value?")
    assert conversation.lead == {"customer_name": "Jane"}
    assert conversation.lead_step == 0
    assert not interaction_store.leads()
    with interaction_store.connect(interaction_store.DEFAULT_DB) as connection:
        saved = connection.execute("SELECT recommended_family_id FROM conversations").fetchone()
    assert saved[0] is None
    assert conversation.recommendation is None
    local_service.handle(conversation, "jane@example.com")
    local_service.handle(conversation, "Tuesday afternoon")
    assert conversation.done
    lead = interaction_store.leads()[0]
    assert lead["email"] == "jane@example.com"
    assert lead["consent_at"]
    result = local_service.handle(conversation, "What is R-value?")
    assert "thermal resistance" in result.reply.casefold()
    assert conversation.done
    result = local_service.handle(conversation, "Thanks")
    assert "welcome" in result.reply
    assert len(interaction_store.leads()) == 1


def test_declining_contact_does_not_block_brief(local_service):
    conversation = agent_core.Conversation()
    local_service.handle(conversation, "My wall is cold")
    local_service.handle(conversation, "finish now")
    local_service.handle(conversation, "skip")
    assert conversation.done
    assert conversation.step == 8
    assert "customer_name" not in conversation.lead


def test_technical_requirement_is_retained_without_closing_intake(local_service):
    conversation = agent_core.Conversation()
    local_service.handle(conversation, "My wall is cold")
    result = local_service.handle(conversation, "NCC and fire requirements apply")
    assert result.category == "product-fit"
    assert not result.done
    assert conversation.review_required
    assert "NCC" in conversation.answers["requirements"]
    assert conversation.step == 1
    assert "customer_name" not in conversation.lead


def test_price_interruption_can_resume_intake(local_service):
    conversation = agent_core.Conversation()
    local_service.handle(conversation, "My wall is cold")
    result = local_service.handle(conversation, "What is the price?")
    assert result.category == "commercial"
    assert conversation.step == 1
    assert not conversation.done
    local_service.handle(conversation, "finish now")
    local_service.handle(conversation, "jane@example.com")
    assert conversation.lead_step == 1


def test_ambiguous_product_can_be_chosen_by_displayed_number(local_service):
    conversation = agent_core.Conversation()
    local_service.handle(conversation, "Tell me about NuWave")
    options = list(conversation.product_options)
    assert len(options) > 1
    result = local_service.handle(conversation, "1")
    assert local_service.product_answers.by_id[options[0]]["name"] in result.reply
    assert conversation.topic_products == [options[0]]
    assert conversation.step == 0


def test_suitability_is_qualified_not_answered_with_a_description(local_service):
    conversation = agent_core.Conversation()
    result = local_service.handle(conversation, "Is NuWrap 5 suitable for my roof?")
    assert result.category == "product-fit"
    assert conversation.step == 1
    assert conversation.recommendation is None
    assert "made from" not in result.reply.casefold()  # Application/project details are still unresolved.


def test_unknown_property_is_not_answered_with_product_purpose(local_service):
    result = local_service.handle(agent_core.Conversation(), "Does NuWrap 5 contain asbestos?")
    assert "don't have confirmed local information" in result.reply
    assert "reducing noise" not in result.reply


def test_named_dimensions_stay_with_family(local_service, monkeypatch):
    import sku_catalogue

    calls = []
    monkeypatch.setattr(sku_catalogue, "available", lambda: True)

    def rows(family_id, **kwargs):
        calls.append(family_id)
        return [{"thickness_mm": 25, "width_mm": 1200, "length_mm": 3000}]

    monkeypatch.setattr(sku_catalogue, "skus_for_family", rows)
    conversation = agent_core.Conversation()
    local_service.handle(conversation, "Tell me about NuWrap 5")
    result = local_service.handle(conversation, "And thickness?")
    assert calls == ["THERMOTEC_NUWRAP_5"]
    assert "25 mm" in result.reply
    assert "Source:" in result.reply
    assert "not a suitability recommendation" in result.reply
    assert conversation.step == 0
    result = local_service.handle(conversation, "Is it available in 50mm thickness?")
    assert "don't have a confirmed 50 mm" in result.reply
    assert "25 mm" not in result.reply


def test_unknown_product_rating_does_not_get_a_generic_definition(local_service):
    result = local_service.handle(agent_core.Conversation(), "What is the R-value of ImaginaryBatt9000?")
    assert "Which product" in result.reply
    assert "thermal resistance" not in result.reply


def test_model_off_knowledge_has_an_explicit_evidence_gap(local_service):
    result = local_service.handle(agent_core.Conversation(), "Explain neutrino foam insulation")
    assert "local information" in result.reply
    assert "Retrieved" not in result.reply
    assert result.retrieval_mode == "none"


def test_unreviewed_performance_values_are_never_quoted(local_service):
    result = local_service.handle(agent_core.Conversation(), "What is NuWave Mass Loaded Vinyl Acoustic Barrier's Rw?")
    assert "verified" in result.reply
    assert "24" not in result.reply
    assert "34" not in result.reply


def test_verified_metric_keeps_variant_context_and_source(local_service):
    local_service.product_answers.evidence["THERMOTEC_NUWRAP_5"] = [{
        "metric_type": "acoustic_rw", "evidence_status": "verified",
        "verified_by": "synthetic-reviewer", "verified_at": "2026-10-01T00:00:00Z",
        "source_locator": "Page 2, table 1", "source_url": "https://example.invalid/synthetic-tds",
        "variant": "synthetic variant", "unit": "dB", "scope": "product",
        "test_context": "Product laboratory test, not installed-system performance.",
        "test_standard": "synthetic-standard", "value": 23, "evidence_id": "TEST-RW",
    }]
    result = local_service.handle(agent_core.Conversation(), "What is NuWrap 5's Rw?")
    for value in ("synthetic variant", "23 dB", "product scope", "Page 2", "TEST-RW", "not a prediction"):
        assert value in result.reply


def test_invalid_verification_metadata_does_not_unlock_a_metric(local_service):
    local_service.product_answers.evidence["THERMOTEC_NUWRAP_5"] = [{
        "metric_type": "acoustic_rw", "evidence_status": "verified", "value": 987,
    }]
    result = local_service.handle(agent_core.Conversation(), "What is NuWrap 5's Rw?")
    assert "verified" in result.reply
    assert "987" not in result.reply


def test_model_failure_keeps_the_same_pending_question(local_service, monkeypatch):
    monkeypatch.setattr(llm_client, "generate_reply", lambda *a, **k: None)
    llm_client._PHRASE_CACHE.clear()
    local_service.use_llm = True
    conversation = agent_core.Conversation()
    result = local_service.handle(conversation, "My external wall is cold")
    assert "existing" in result.reply
    assert conversation.step == 1


def test_model_cannot_invent_a_dimension_in_a_question(local_service, monkeypatch):
    monkeypatch.setattr(llm_client, "generate_reply", lambda *a, **k: "Would you like our 50mm insulation?")
    llm_client._PHRASE_CACHE.clear()
    local_service.use_llm = True
    result = local_service.handle(agent_core.Conversation(), "My external wall is cold")
    assert "50mm" not in result.reply
    assert "existing" in result.reply


def test_capture_is_deterministic_even_with_local_wording_enabled(local_service, monkeypatch):
    monkeypatch.setattr(llm_client, "generate_reply", lambda *a, **k: pytest.fail("Consent/capture must not use model wording"))
    llm_client._PHRASE_CACHE.clear()
    local_service.use_llm = True
    conversation = agent_core.Conversation()
    result = local_service.handle(conversation, "My external wall is cold")
    assert "existing" in result.reply
    assert conversation.step == 1


def test_local_model_cannot_ask_for_product_name_instead_of_customer_name(local_service, monkeypatch):
    monkeypatch.setattr(llm_client, "generate_reply", lambda *a, **k: "Would you like me to use a specific name for the product, or skip that step?")
    llm_client._PHRASE_CACHE.clear()
    local_service.use_llm = True
    result = local_service.handle(agent_core.Conversation(), "My wall is cold")
    assert "internal" in result.reply
    assert "name for the product" not in result.reply


def test_unreviewed_retrieval_terms_cannot_change_application_eligibility():
    from bot_engine import family_elements, rank_families

    pipe = {
        "family_id": "SYNTHETIC_PIPE", "name": "Synthetic Pipe", "manufacturer": "Test",
        "category": "Pipe lagging", "applications": ["pipe", "wall"],
        "keywords": ["pipe", "wall", "thermal", "cold"],
        "documented_applications": ["pipe"], "documented_keywords": ["pipe"],
        "scores": {key: 5 for key in agent_core.PRIORITY_LABELS},
        "confidence": "manufacturer_supported",
    }
    assert family_elements(pipe) == {"pipe_duct"}
    assert rank_families([pipe], {"application": "external wall", "priority": "thermal"}) == []


def test_reference_in_an_intake_statement_does_not_trigger_product_answer(local_service):
    conversation = agent_core.Conversation()
    local_service.handle(conversation, "Tell me about NuWrap 5")
    local_service.handle(conversation, "Help me choose insulation for my wall")
    local_service.handle(conversation, "My name is Jane")
    result = local_service.handle(conversation, "It is thermal comfort that matters")
    assert result.category == "product-fit"
    assert conversation.answers["priority"] == "It is thermal comfort that matters"


def test_callback_request_does_not_force_product_selection(local_service):
    conversation = agent_core.Conversation()
    result = local_service.handle(conversation, "Can someone call me?")
    assert result.category == "callback"
    assert agent_core.LEAD_CONSENT_TEXT in result.reply
    assert conversation.recommendation is None
    local_service.handle(conversation, "invoice@example.com")
    local_service.handle(conversation, "Tuesday")
    assert interaction_store.leads()[0]["email"] == "invoice@example.com"
    assert conversation.done


def test_old_session_state_still_resumes(local_service):
    conversation = agent_core.Conversation.from_dict({"step": 1, "answers": {"problem": "my wall is cold"}})
    result = local_service.handle(conversation, "What is R-value?")
    assert result.category == "informational"
    assert conversation.step == 1
    assert conversation.mode == "discovery"


def test_completed_project_can_start_a_separate_enquiry(local_service):
    conversation = agent_core.Conversation(done=True, step=8, answers={"problem": "old wall enquiry"})
    old_id = conversation.conversation_id
    local_service.handle(conversation, "New project: my roof is hot")
    assert conversation.conversation_id != old_id
    assert not conversation.done
    assert conversation.step == 1
    assert "old wall" not in conversation.answers["problem"]


def test_evaluation_keeps_default_store_and_never_requests_network(monkeypatch):
    from scripts.eval_customer_conversations import evaluate

    original = interaction_store.DEFAULT_DB
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("Default evaluation must not use a network"))
    report = evaluate(names=["known-product", "resume-name", "requirements-answer"])
    assert report["passed"] == report["cases"] == 3
    assert report["model_calls"] == []
    assert interaction_store.DEFAULT_DB == original


def test_element_correction_during_contact_requalifies_constraints(local_service):
    conversation = agent_core.Conversation(
        step=8, mode="selection", lead={"customer_name": "Jane"},
        answers={"problem": "cold external wall", "name": "Jane", "application": "wall",
                 "priority": "thermal comfort", "conditions": "90mm wall cavity",
                 "project": "residential retrofit", "locality": "Sydney 2000", "requirements": "none"},
    )
    result = local_service.handle(conversation, "Actually it is the roof, not the wall")
    assert conversation.step == 8  # Legacy contact stage honours the already-offered consent.
    assert "conditions" not in conversation.answers
    assert "roof" in conversation.answers["application"]
    assert "updated" in result.reply.casefold()
    assert "phone" not in conversation.lead


def test_name_only_opening_does_not_become_project_problem(local_service):
    conversation = agent_core.Conversation()
    local_service.handle(conversation, "My name is Jane")
    assert conversation.step == 0
    assert "problem" not in conversation.answers
    assert conversation.lead["customer_name"] == "Jane"


def test_glossary_cannot_override_a_compliance_escalation(local_service):
    result = local_service.handle(agent_core.Conversation(), "What is NCC?")
    assert result.category == "escalate"
    assert "cannot confirm" in result.reply
