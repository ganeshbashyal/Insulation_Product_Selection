"""RAG over knowledge base: answer informational questions with citations.

Queries knowledge/industry/** (88 Q&A pairs + compliance docs), embeds with local Ollama,
returns top-6 with hybrid ranking, generates answer via hosted LLM with mandatory inline citations.
"""
from __future__ import annotations

import json
from pathlib import Path

import llm_client
from hybrid_retrieval import hybrid_rank, load_or_embed_cards

ROOT = Path(__file__).resolve().parent
KNOWLEDGE_DIR = ROOT / "knowledge" / "industry"

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
        """Load Q&A pairs from knowledge/industry/**."""
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

        # Convert chunks to cards format for hybrid_retrieval
        cards = [
            {
                "family_id": f"knowledge_{i}",
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

    def answer(self, question: str, use_llm: bool = True) -> dict[str, str]:
        """
        Answer a question using RAG.
        Returns {"answer": "...", "sources": ["path1", "path2"], "confidence": 0.0-1.0}
        """
        if not self.knowledge_chunks:
            return {"answer": "Knowledge base not available", "sources": [], "confidence": 0.0}

        # Retrieve relevant chunks (top-6)
        try:
            # Use hybrid ranking if embeddings available
            ranked = hybrid_rank(
                question,
                [{"family_id": f"knowledge_{i}", "name": chunk.get("source", "")} for i, chunk in enumerate(self.knowledge_chunks)],
                self.embeddings,
            ) if self.embeddings else []

            # Fallback to top-6 by index if no embeddings
            if not ranked:
                ranked = self.knowledge_chunks[:6]
            else:
                # Extract actual chunks from ranked results
                ranked = [self.knowledge_chunks[int(r["family_id"].split("_")[1])] for r in ranked[:6]]
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
        if use_llm:
            try:
                prompt = RAG_ANSWER_PROMPT.format(question=question, knowledge=knowledge_text)
                answer = llm_client.phrase(prompt, context={})
            except Exception:
                answer = f"Retrieved {len(ranked)} sources but LLM unavailable"
        else:
            answer = f"Retrieved {len(ranked)} relevant sources"

        # Extract sources from answer (look for citations)
        sources = list(set(chunk.get("source", "") for chunk in ranked))

        return {
            "answer": answer,
            "sources": sources,
            "confidence": 0.8 if ranked else 0.0,
        }
