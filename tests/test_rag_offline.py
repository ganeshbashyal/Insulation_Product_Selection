"""Offline RAG must start and retrieve without waiting for a local model."""
from __future__ import annotations

import rag_answerer
from rag_answerer import RAGAnswerer


def test_initialisation_does_not_probe_or_embed(monkeypatch):
    RAGAnswerer.reset_cache()
    monkeypatch.setattr(
        rag_answerer,
        "embeddings_available",
        lambda: (_ for _ in ()).throw(AssertionError("startup must stay lazy")),
    )

    answerer = RAGAnswerer()

    assert answerer.knowledge_chunks
    assert answerer.embeddings == {}


def test_offline_ranking_uses_lexical_fallback(monkeypatch):
    RAGAnswerer.reset_cache()
    monkeypatch.setattr(rag_answerer, "embeddings_available", lambda: False)
    answerer = RAGAnswerer()

    ranked = answerer._rank_chunks("condensation vapour permeance")

    assert ranked
    assert answerer.embeddings == {}


def test_answer_without_model_never_probes_embeddings(monkeypatch):
    monkeypatch.setattr(rag_answerer, "embeddings_available", lambda: (_ for _ in ()).throw(AssertionError("model-off must be offline")))
    answerer = RAGAnswerer()
    answerer.knowledge_chunks = [{"text": "Condensation occurs when water vapour condenses on a cold surface.", "topic": "Condensation"}]
    result = answerer.answer("Explain condensation", use_llm=False)
    assert "water vapour" in result["answer"]
    assert "Source:" in result["answer"]
    assert "Retrieved" not in result["answer"]


def test_retrieval_failure_never_uses_unrelated_first_chunks(monkeypatch):
    answerer = RAGAnswerer()
    monkeypatch.setattr(answerer, "_rank_chunks", lambda *a, **k: (_ for _ in ()).throw(OSError("synthetic read failure")))
    result = answerer.answer("Explain condensation", use_llm=False)
    assert result["retrieval_mode"] == "unavailable"
    assert result["sources"] == []
