"""Hybrid retrieval: dense embeddings + RRF fusion with lexical ranking.

Embeds the retrieval cards locally via Ollama (nomic-embed-text by default),
caches to `data/processed/family_embeddings.npz` keyed by card content hash so
they rebuild only when cards change. Fuses lexical rank (from bot_engine) with
dense cosine similarity via Reciprocal Rank Fusion (RRF).

All computation is local: no external APIs, no vector DB, numpy arrays only.

Usage:
    from hybrid_retrieval import hybrid_rank
    ranked = hybrid_rank(enquiry_text, families, alpha=0.5)  # 50/50 lexical/dense
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
EMBEDDINGS_CACHE = ROOT / "data" / "processed" / "family_embeddings.npz"


def _ollama_embed(text: str) -> list[float] | None:
    """Embed a single text via local Ollama. Returns None if server unavailable."""
    if not text or not isinstance(text, str):
        return None
    payload = {
        "model": OLLAMA_EMBED_MODEL,
        "prompt": text.strip(),
    }
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/embeddings",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
            embedding = data.get("embedding")
            return embedding if isinstance(embedding, list) else None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, KeyError):
        return None


def _card_hash(card_text: str) -> str:
    """Deterministic hash of a card's text, used as the cache key."""
    return hashlib.sha256(card_text.encode("utf-8")).hexdigest()[:16]


def load_or_embed_cards(cards: list[dict]) -> tuple[dict[str, np.ndarray], dict[str, str]]:
    """Load embeddings from cache or embed fresh. Returns ({family_id -> embedding}, {family_id -> card_hash})."""
    EMBEDDINGS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    embeddings: dict[str, np.ndarray] = {}

    # Build the set of cards we need
    card_map: dict[str, dict] = {c["family_id"]: c for c in cards}
    needed_ids = set(card_map.keys())

    # Try to load from cache
    if EMBEDDINGS_CACHE.exists():
        try:
            npz = np.load(EMBEDDINGS_CACHE, allow_pickle=True)
            cached_hashes = dict(npz["hashes"].item() or {})
            cached_family_ids = npz.get("family_ids", [])
            cached_embedding_array = npz.get("embeddings")

            # Re-associate embeddings with family IDs
            if cached_embedding_array is not None and len(cached_family_ids) > 0:
                for i, fid in enumerate(cached_family_ids):
                    fid = str(fid)  # numpy string might need conversion
                    card = card_map.get(fid)
                    if not card:
                        continue
                    card_text = card.get("text", "")
                    new_hash = _card_hash(card_text)
                    if cached_hashes.get(fid) == new_hash:
                        embeddings[fid] = cached_embedding_array[i]
                        hashes[fid] = new_hash
                        needed_ids.discard(fid)
        except (OSError, ValueError, KeyError, IndexError):
            pass

    # Embed any cards not in cache or whose content changed
    if needed_ids:
        print(f"embedding {len(needed_ids)} card(s) (cache: {len(embeddings)} hit, {len(needed_ids)} miss)")
        for fid in sorted(needed_ids):
            card = card_map[fid]
            card_text = card.get("text", "")
            embedding = _ollama_embed(card_text)
            if embedding is not None:
                embeddings[fid] = np.array(embedding, dtype=np.float32)
                hashes[fid] = _card_hash(card_text)
            else:
                print(f"  warning: embedding failed for {fid}")

    # Write cache
    if embeddings:
        # Store as: family_ids array, embeddings matrix, hashes dict
        sorted_ids = sorted(embeddings.keys())
        embedding_matrix = np.array([embeddings[fid] for fid in sorted_ids], dtype=np.float32)
        np.savez(
            EMBEDDINGS_CACHE,
            embeddings=embedding_matrix,
            family_ids=np.array(sorted_ids),
            hashes=np.array(hashes, dtype=object),
        )

    return embeddings, hashes


def _rrf_score(lexical_rank: int, dense_rank: int, k: int = 60) -> float:
    """Reciprocal Rank Fusion: 1/(k + rank). Scale-free, no calibration needed."""
    return 1.0 / (k + lexical_rank) + 1.0 / (k + dense_rank)


def hybrid_rank(
    enquiry_text: str,
    families: list[dict],
    embeddings: dict[str, np.ndarray],
    alpha: float = 0.5,
    lexical_ranker=None,
) -> list[dict]:
    """
    Rank families by hybrid (lexical + dense) relevance.

    Args:
        enquiry_text: The customer's enquiry
        families: List of family dicts from agent_core.FAMILIES
        embeddings: Dict of {family_id -> embedding vector} from load_or_embed_cards
        alpha: Blend weight (unused; RRF is scale-free, this is for future tuning)
        lexical_ranker: Callable that ranks families (default: bot_engine.rank_families)

    Returns:
        Ranked list of families, each augmented with:
        - lexical_rank: Position in lexical ranking (0 = top)
        - dense_rank: Position in dense ranking (0 = top)
        - rrf_score: RRF fusion score
    """
    if lexical_ranker is None:
        from bot_engine import rank_families
        lexical_ranker = rank_families

    # Lexical ranking
    answers = {
        "problem": enquiry_text[:500],  # cap to avoid ranker slowdown
        "application": "", "priority": "", "conditions": "", "project": "",
        "locality": "", "requirements": "", "contact": "",
    }
    lexical_ranked = lexical_ranker(families, answers, "Compare both")

    # Dense ranking: embed the enquiry, score cosine similarity
    enquiry_emb = _ollama_embed(enquiry_text[:500])
    if enquiry_emb is None:
        # Ollama unavailable; fall back to lexical only
        return lexical_ranked

    enquiry_vec = np.array(enquiry_emb, dtype=np.float32)
    dense_scores: dict[str, float] = {}
    for fid in {f["family_id"] for f in families}:
        if fid in embeddings:
            card_vec = embeddings[fid]
            # cosine similarity
            norm_q = np.linalg.norm(enquiry_vec)
            norm_c = np.linalg.norm(card_vec)
            if norm_q > 0 and norm_c > 0:
                dense_scores[fid] = float(np.dot(enquiry_vec, card_vec) / (norm_q * norm_c))
            else:
                dense_scores[fid] = 0.0

    # Rank by dense score (for RRF)
    dense_ranked_ids = sorted(dense_scores.keys(), key=lambda fid: dense_scores[fid], reverse=True)
    dense_rank_map = {fid: i for i, fid in enumerate(dense_ranked_ids)}

    # Fuse: map lexical rank + dense rank -> RRF score, re-sort
    fused = []
    lexical_rank_map = {f["family_id"]: i for i, f in enumerate(lexical_ranked)}

    for family in lexical_ranked:
        fid = family["family_id"]
        lex_rank = lexical_rank_map.get(fid, len(lexical_ranked))
        dense_rank = dense_rank_map.get(fid, len(dense_ranked_ids))
        rrf_score = _rrf_score(lex_rank, dense_rank)

        fused.append({
            **family,
            "lexical_rank": lex_rank,
            "dense_rank": dense_rank,
            "dense_score": dense_scores.get(fid, 0.0),
            "rrf_score": rrf_score,
        })

    # Re-sort by RRF score
    return sorted(fused, key=lambda f: (f["rrf_score"], f.get("match_score", 0)), reverse=True)
