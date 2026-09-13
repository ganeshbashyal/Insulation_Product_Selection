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
