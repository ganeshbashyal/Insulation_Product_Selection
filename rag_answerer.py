"""Retrieve general local references, without inventing an answer.

Product properties use the separate governed product-answer path. This reader
returns a relevant source excerpt; optional dense retrieval stays local.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import numpy as np

from hybrid_retrieval import _ollama_embed, embeddings_available, load_or_embed_cards

ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger(__name__)
KNOWLEDGE_DIR = ROOT / "knowledge" / "industry"

def _citation_label(chunk: dict) -> str:
    """Human-readable citation for a chunk.

    The raw source is the JSONL filename, which is identical for every chunk in
    a file and so is useless as a citation. Prefer the chunk's topic.
    """
    topic = (chunk.get("topic") or "").strip()
    if topic:
        module = (chunk.get("module_title") or "").strip()
        # Skip the module when it repeats the topic (topic "Class 10 Garages"
        # under module "Class 10") or is a generic corpus-level title that adds
        # length without telling the reader anything.
        generic = module.lower().endswith(("profiles", "corpus", "knowledge base"))
        if module and not generic and module.lower() not in topic.lower():
            return f"{topic} - {module}"
        return topic
    return (chunk.get("source") or "unknown").strip()


class RAGAnswerer:
    """Answer informational questions using RAG over knowledge base."""

    # The corpus is read-only and identical for every instance, so load and
    # embed it once per process. Without this, each construction re-embedded
    # ~1,100 chunks: FastAPI paid it on every worker start and the test suite
    # paid it once per fixture, which is what pushed a full run past 55 minutes.
    _shared_chunks: list[dict] | None = None
    _shared_embeddings: dict | None = None

    def __init__(self, eager_embeddings: bool = False):
        cls = type(self)
        if cls._shared_chunks is None:
            cls._shared_chunks = self._load_knowledge_base()
        self.knowledge_chunks = cls._shared_chunks
        self.embeddings = cls._shared_embeddings or {}
        if eager_embeddings:
            self._ensure_embeddings()

    @classmethod
    def reset_cache(cls) -> None:
        """Drop the process-wide corpus cache (tests, or after a corpus rebuild)."""
        cls._shared_chunks = None
        cls._shared_embeddings = None

    def _load_knowledge_base(self) -> list[dict]:
        """Load Q&A pairs and RAG chunks from knowledge/industry/**."""
        chunks = []
        if not KNOWLEDGE_DIR.exists():
            return chunks

        # Load qa_pairs.jsonl
        qa_path = KNOWLEDGE_DIR / "qa_pairs.jsonl"
        if qa_path.exists():
            with open(qa_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            chunk = json.loads(line)
                            chunk["source"] = "qa_pairs.jsonl"
                            chunks.append(chunk)
                        except json.JSONDecodeError:
                            pass

        # Load generated RAG chunk files (e.g. building-class construction stages)
        for jsonl_path in sorted((KNOWLEDGE_DIR / "training").glob("*_rag_chunks.jsonl")):
            with open(jsonl_path, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("text"):
                        chunk["source"] = jsonl_path.name
                        chunks.append(chunk)

        # Raw compliance sources (both NCC volumes, ABCB handbooks, industry
        # reports) and the curated markdown are chunked ahead of time by
        # scripts/build_compliance_chunks.py into compliance_rag_chunks.jsonl,
        # which the loop above picks up. Splitting them here on blank lines
        # would strip the clause ids and page numbers that make them citable.

        return chunks

    def _load_embeddings(self) -> None:
        """Load or create embeddings for knowledge chunks."""
        if not self.knowledge_chunks:
            return

        # The embedding must cover the chunk's own text. Embedding the source
        # filename instead would make every chunk from one file identical.
        cards = [
            {
                "family_id": f"knowledge_{i}",
                "name": chunk.get("topic") or chunk.get("source", ""),
                "text": chunk.get("text", chunk.get("content", "")),
                "source": chunk.get("source", "unknown"),
            }
            for i, chunk in enumerate(self.knowledge_chunks)
        ]

        try:
            self.embeddings, _ = load_or_embed_cards(cards, namespace="knowledge")
        except Exception:
            # If embedding fails (Ollama not running), continue with empty embeddings
            self.embeddings = {}

    def _ensure_embeddings(self) -> None:
        """Load dense vectors only when the local provider is reachable."""
        cls = type(self)
        if cls._shared_embeddings is not None:
            self.embeddings = cls._shared_embeddings
            return
        if not embeddings_available():
            self.embeddings = {}
            return
        self._load_embeddings()
        cls._shared_embeddings = self.embeddings

    def _rank_chunks(self, question: str, top_k: int = 6, *, use_embeddings: bool = True) -> list[dict]:
        """Rank knowledge chunks against the question.

        Uses dense cosine similarity when embeddings are available, and falls
        back to keyword overlap so retrieval still discriminates when Ollama is
        unreachable.
        """
        if use_embeddings:
            self._ensure_embeddings()
        query_vec = None
        if use_embeddings and self.embeddings:
            try:
                raw = _ollama_embed(question[:2000])
                if raw:
                    query_vec = np.asarray(raw, dtype=np.float32)
                    norm = np.linalg.norm(query_vec)
                    query_vec = query_vec / norm if norm > 0 else None
            except Exception:
                query_vec = None

        scored: list[tuple[float, dict]] = []
        if query_vec is not None:
            for i, chunk in enumerate(self.knowledge_chunks):
                vec = self.embeddings.get(f"knowledge_{i}")
                if vec is None:
                    continue
                vec = np.asarray(vec, dtype=np.float32)
                norm = np.linalg.norm(vec)
                if norm <= 0:
                    continue
                scored.append((float(np.dot(query_vec, vec / norm)), chunk))

        if not scored:
            terms = {t for t in re.findall(r"[a-z0-9]+", question.lower()) if len(t) > 2}
            for chunk in self.knowledge_chunks:
                text = chunk.get("text", chunk.get("content", "")).lower()
                if not terms:
                    continue
                hits = sum(1 for t in terms if t in text)
                if hits:
                    scored.append((hits / len(terms), chunk))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [chunk for _, chunk in scored[:top_k]]

    def answer(self, question: str, use_llm: bool = True) -> dict:
        """
        Answer a question using RAG.
        Returns {"answer": "...", "sources": ["path1", "path2"], "confidence": 0.0-1.0}
        """
        if not self.knowledge_chunks:
            return {"answer": "Knowledge base not available", "sources": [], "confidence": 0.0, "retrieval_mode": "unavailable"}

        if re.search(r"\b(?:rating|performance|density|r[\s-]?value|rw|nrc)\b", question, re.I):
            return {"answer": "I need the exact product and verified performance evidence to answer that property. Which product do you mean?", "sources": [], "confidence": 0.0, "retrieval_mode": "none"}

        try:
            ranked = self._rank_chunks(question, use_embeddings=use_llm)
        except (OSError, ValueError, RuntimeError):
            LOGGER.exception("Knowledge retrieval failed")
            return {"answer": "I couldn't read the local knowledge for that question. Please ask the team to check it.", "sources": [], "confidence": 0.0, "retrieval_mode": "unavailable"}

        if not ranked:
            return {"answer": "No relevant information found", "sources": [], "confidence": 0.0, "retrieval_mode": "none"}

        # Generic word overlap is not evidence that a source answers a query.
        stop = {"what", "which", "where", "when", "does", "this", "that", "about", "tell", "explain", "have", "with", "your", "from", "information", "insulation", "please"}
        terms = {term for term in re.findall(r"[a-z0-9]+", question.lower()) if len(term) > 2} - stop
        ranked = [
            chunk for chunk in ranked
            if terms and sum(term in chunk.get("text", chunk.get("content", "")).lower() for term in terms) / len(terms) >= 0.7
        ]
        if not ranked:
            return {"answer": "I don't have enough relevant local information to answer that. Please share the product name or the specific detail you need.", "sources": [], "confidence": 0.0, "retrieval_mode": "none"}

        excerpt = ranked[0].get("text", ranked[0].get("content", "")).strip()
        excerpt = re.split(r"(?<=[.!?])\s+", excerpt)[0]
        if len(excerpt) > 500 or re.search(r"\b(?:R\d|Rw\s*\d|NRC\s*\d|\d+(?:\.\d+)?\s*(?:mm|dB|kg|%))", excerpt, re.I):
            return {"answer": "The local source needs a more specific question before I can give a concise answer. What detail do you need?", "sources": [], "confidence": 0.0, "retrieval_mode": "none"}
        answer = f"From the local reference: {excerpt}\nSource: {_citation_label(ranked[0])}."

        # Extract sources from answer (look for citations)
        sources = list(dict.fromkeys(_citation_label(chunk) for chunk in ranked))

        return {
            "answer": answer,
            "sources": sources,
            "confidence": 0.8 if ranked else 0.0,
            "retrieval_mode": "dense" if use_llm and self.embeddings else "lexical",
        }
