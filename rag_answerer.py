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
3. Cite inline like [this](path/to/source) for EVERY claim
4. If sources don't cover the question, say "I don't have enough information about that"
5. Never make up information or cite sources that weren't provided

Answer:
"""


class RAGAnswerer:
    """Answer informational questions using RAG over knowledge base."""

    def __init__(self):
        self.knowledge_chunks = self._load_knowledge_base()
        self.embeddings = {}
        self._load_embeddings()

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

        # Load other .txt files as chunks
        for txt_file in KNOWLEDGE_DIR.glob("*.txt"):
            with open(txt_file, encoding="utf-8") as f:
                text = f.read()
                # Split into paragraphs
                for para in text.split("\n\n"):
                    if para.strip():
                        chunks.append({
                            "text": para.strip(),
                            "source": txt_file.name,
                        })

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
            self.embeddings, _ = load_or_embed_cards(cards)
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
            source = chunk.get("source", "unknown")
            text = chunk.get("text", chunk.get("content", ""))
            knowledge_text += f"[{i+1}] ({source}): {text}\n\n"

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
                    answer = reply.strip()
                else:
                    answer = f"Retrieved {len(ranked)} sources but LLM unavailable"
            except Exception:
                answer = f"Retrieved {len(ranked)} sources but LLM unavailable"

        # Extract sources from answer (look for citations)
        sources = list(set(chunk.get("source", "") for chunk in ranked))

        return {
            "answer": answer,
            "sources": sources,
            "confidence": 0.8 if ranked else 0.0,
        }
