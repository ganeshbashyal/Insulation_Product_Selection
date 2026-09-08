"""RAG over knowledge base: answer informational questions with citations.

Queries knowledge/industry/** (Q&A pairs, generated RAG chunks and compliance
docs), embeds with local Ollama, returns the top-6 by dense similarity and
generates an answer via the local LLM with mandatory inline citations.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import numpy as np

import llm_client
from hybrid_retrieval import _ollama_embed, load_or_embed_cards

ROOT = Path(__file__).resolve().parent
KNOWLEDGE_DIR = ROOT / "knowledge" / "industry"

# A grounded RAG answer sends several KB of context, so it needs a longer
# deadline than the short conversational rephrases llm_client defaults to.
RAG_TIMEOUT_SECONDS = float(os.environ.get("RAG_TIMEOUT_SECONDS", "120"))

RAG_SYSTEM_PROMPT = (
    "You are an Australian insulation and construction assistant. Answer only "
    "from the knowledge sources supplied in the user message. Cite the source "
    "for every claim. If the sources do not cover the question, say so plainly. "
    "Never assert that a product or build-up is NCC-compliant; compliance is "
    "determined by the project's certifier."
)

RAG_ANSWER_PROMPT = """Based ONLY on these knowledge sources, answer the customer's question.

Question: {question}

Knowledge:
{knowledge}

Requirements:
1. Answer concisely (2-3 sentences max)
2. Use ONLY information from the knowledge sources above
3. Cite with the bracketed number of the source, e.g. [1] or [2], at the end of
   each sentence it supports. Cite each source once per sentence - never repeat
   the same marker several times in one sentence.
4. If sources don't cover the question, say "I don't have enough information about that"
5. Never make up information or cite sources that weren't provided
6. Write in plain text. Never use LaTeX or maths markup - write ">=" not "\\ge",
   and "->" not "\\rightarrow".

Answer:
"""


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


def _expand_citations(text: str, ranked: list[dict]) -> str:
    """Rewrite the model's [n] markers into readable [topic](topic) links.

    Small local models emit numeric markers far more reliably than they
    reproduce long labels, so we ask for [n] and resolve it deterministically
    here. Out-of-range markers are dropped rather than shown to the customer.
    """
    def replace(match: re.Match) -> str:
        labels = []
        for raw in re.split(r"[,\s]+", match.group(1)):
            if not raw.isdigit():
                continue
            idx = int(raw)
            if 1 <= idx <= len(ranked):
                label = _citation_label(ranked[idx - 1])
                if label not in labels:
                    labels.append(label)
        return "".join(f"[{lab}]({lab})" for lab in labels)

    # Models group markers as [5, 6] as well as [5], so accept both forms.
    text = re.sub(r"\[(\d+(?:\s*,\s*\d+)*)\]", replace, text)
    return re.sub(r"\s+([.,;])", r"\1", text).strip()


class RAGAnswerer:
    """Answer informational questions using RAG over knowledge base."""

    # The corpus is read-only and identical for every instance, so load and
    # embed it once per process. Without this, each construction re-embedded
    # ~1,100 chunks: FastAPI paid it on every worker start and the test suite
    # paid it once per fixture, which is what pushed a full run past 55 minutes.
    _shared_chunks: list[dict] | None = None
    _shared_embeddings: dict | None = None

    def __init__(self):
        cls = type(self)
        if cls._shared_chunks is None:
            cls._shared_chunks = self._load_knowledge_base()
        self.knowledge_chunks = cls._shared_chunks

        if cls._shared_embeddings is None:
            self.embeddings = {}
            self._load_embeddings()
            cls._shared_embeddings = self.embeddings
        else:
            self.embeddings = cls._shared_embeddings

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
            pass

    def _rank_chunks(self, question: str, top_k: int = 6) -> list[dict]:
        """Rank knowledge chunks against the question.

        Uses dense cosine similarity when embeddings are available, and falls
        back to keyword overlap so retrieval still discriminates when Ollama is
        unreachable.
        """
        query_vec = None
        if self.embeddings:
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

    def answer(self, question: str, use_llm: bool = True) -> dict[str, str]:
        """
        Answer a question using RAG.
        Returns {"answer": "...", "sources": ["path1", "path2"], "confidence": 0.0-1.0}
        """
        if not self.knowledge_chunks:
            return {"answer": "Knowledge base not available", "sources": [], "confidence": 0.0}

        try:
            ranked = self._rank_chunks(question)
        except Exception:
            ranked = self.knowledge_chunks[:6]

        if not ranked:
            return {"answer": "No relevant information found", "sources": [], "confidence": 0.0}

        # Format knowledge for prompt
        knowledge_text = ""
        for i, chunk in enumerate(ranked):
            label = _citation_label(chunk)
            text = chunk.get("text", chunk.get("content", ""))
            knowledge_text += f"[{i+1}] ({label}): {text}\n\n"

        # Generate answer via LLM
        answer = f"Retrieved {len(ranked)} relevant sources"
        if use_llm:
            try:
                prompt = RAG_ANSWER_PROMPT.format(question=question, knowledge=knowledge_text)
                # generate_reply returns None when Ollama is unavailable; phrase()
                # would echo the prompt back as its fallback text, so call the
                # generator directly and keep the deterministic fallback here.
                reply = llm_client.generate_reply(
                    RAG_SYSTEM_PROMPT, prompt, max_tokens=400, timeout=RAG_TIMEOUT_SECONDS
                )
                if reply and reply.strip():
                    answer = _expand_citations(reply.strip(), ranked)
                else:
                    answer = f"Retrieved {len(ranked)} sources but LLM unavailable"
            except Exception:
                answer = f"Retrieved {len(ranked)} sources but LLM unavailable"

        # Extract sources from answer (look for citations)
        sources = list(dict.fromkeys(_citation_label(chunk) for chunk in ranked))

        return {
            "answer": answer,
            "sources": sources,
            "confidence": 0.8 if ranked else 0.0,
        }
