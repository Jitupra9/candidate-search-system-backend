"""
RAG Service — Retriever Strategies
=====================================

Individual strategies (selectable):
  similarity    → Top-k cosine similarity, fast
  mmr           → Max Marginal Relevance, diverse results
  multi_query   → LLM expands query into variants, merges recall
  contextual    → LLM trims irrelevant passage parts
  self_query    → LLM extracts metadata filter from natural language
  hybrid_bm25   → BM25 keyword + dense vector, RRF fusion
  ensemble      → Weighted merge of similarity + MMR

Full pipeline (recommended default):
  pipeline      → multi_query → similarity pool → MMR → contextual compression
                  Best recall + diversity + clean context in one pass

Parent-Child Pattern:
  child chunk    → small text embedded in ChromaDB (fast vector search)
  parent_content → full passage stored in metadata (no second collection needed)
  search finds child → parent_content already in metadata → inject into LLM
"""
import json
import logging
import math
from typing import Literal
from app.core.chroma_client import chroma
from app.services.Embadding import EmbeddingService
from app.llm.prompts import MULTI_QUERY_PROMPT, CONTEXTUAL_COMPRESSION_PROMPT, SELF_QUERY_PROMPT

logger = logging.getLogger(__name__)

RetrievalStrategy = Literal[
    "pipeline",
    "similarity", "mmr", "multi_query",
    "contextual", "self_query", "hybrid_bm25", "ensemble",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_result(doc: str, meta: dict, score: float = 1.0) -> dict:
    return {
        "child_chunk":    doc,
        "parent_content": meta.get("parent_content") or doc,
        "candidate_id":   meta.get("candidate_id", ""),
        "parent_index":   meta.get("parent_index", -1),
        "file_type":      meta.get("file_type", ""),
        "score":          round(score, 4),
    }


def _rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank + 1)


def _deduplicate(results: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for r in results:
        key = (r["candidate_id"], r["parent_index"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


# ── Similarity ────────────────────────────────────────────────────────────────

def _similarity(query_vector: list, k: int, filters: dict) -> list[dict]:
    """Top-k cosine similarity — embeds query, finds k nearest child chunks."""
    where = filters if filters else None
    results = chroma.collection.query(
        query_embeddings=[query_vector],
        n_results=k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    return [
        _build_result(doc, meta, score=1 - dist)
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ]


# ── MMR ───────────────────────────────────────────────────────────────────────

def _mmr_from_pool(
    pool: list[dict],
    query_vector: list,
    k: int,
    lambda_mult: float = 0.5,
) -> list[dict]:
    """
    MMR selection from an already-fetched pool of results.
    Avoids a second ChromaDB call — used internally by the pipeline.
    lambda_mult: 1.0 = pure relevance, 0.0 = pure diversity
    """
    if not pool:
        return []

    # We need embeddings for MMR — re-fetch with embeddings for pool candidates
    candidate_ids = list({
        f"{r['candidate_id']}_p{r['parent_index']}" for r in pool
    })

    # Build lookup from pool
    pool_lookup = {
        f"{r['candidate_id']}_p{r['parent_index']}": r for r in pool
    }

    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na  = math.sqrt(sum(x ** 2 for x in a))
        nb  = math.sqrt(sum(x ** 2 for x in b))
        return dot / (na * nb + 1e-9)

    # Re-query ChromaDB with embeddings for just the pool items
    # Use query to get their stored embeddings
    fetch_k = min(len(pool) * 2, 50)
    results = chroma.collection.query(
        query_embeddings=[query_vector],
        n_results=fetch_k,
        include=["documents", "metadatas", "distances", "embeddings"],
    )

    docs       = results["documents"][0]
    metas      = results["metadatas"][0]
    dists      = results["distances"][0]
    embeddings = results["embeddings"][0]

    # Filter to only items in our pool
    pool_indices = [
        i for i, meta in enumerate(metas)
        if f"{meta.get('candidate_id')}_p{meta.get('parent_index')}" in pool_lookup
    ]

    if not pool_indices:
        return pool[:k]

    selected  = []
    remaining = list(pool_indices)

    for _ in range(min(k, len(pool_indices))):
        if not remaining:
            break
        if not selected:
            best = min(remaining, key=lambda i: dists[i])
        else:
            best = max(
                remaining,
                key=lambda i: lambda_mult * (1 - dists[i])
                - (1 - lambda_mult) * max(
                    cosine(embeddings[i], embeddings[j]) for j in selected
                ),
            )
        selected.append(best)
        remaining.remove(best)

    return [_build_result(docs[i], metas[i], 1 - dists[i]) for i in selected]


def _mmr(query_vector: list, k: int, filters: dict, lambda_mult: float = 0.5) -> list[dict]:
    """
    MMR standalone — fetches fetch_k candidates then applies MMR selection.
    lambda_mult: 1.0 = pure relevance, 0.0 = pure diversity, 0.5 = balanced
    """
    where = filters if filters else None
    fetch_k = min(k * 4, 50)
    results = chroma.collection.query(
        query_embeddings=[query_vector],
        n_results=fetch_k,
        where=where,
        include=["documents", "metadatas", "distances", "embeddings"],
    )

    docs       = results["documents"][0]
    metas      = results["metadatas"][0]
    dists      = results["distances"][0]
    embeddings = results["embeddings"][0]

    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na  = math.sqrt(sum(x ** 2 for x in a))
        nb  = math.sqrt(sum(x ** 2 for x in b))
        return dot / (na * nb + 1e-9)

    selected  = []
    remaining = list(range(len(docs)))

    for _ in range(min(k, len(docs))):
        if not remaining:
            break
        if not selected:
            best = min(remaining, key=lambda i: dists[i])
        else:
            best = max(
                remaining,
                key=lambda i: lambda_mult * (1 - dists[i])
                - (1 - lambda_mult) * max(
                    cosine(embeddings[i], embeddings[j]) for j in selected
                ),
            )
        selected.append(best)
        remaining.remove(best)

    return [_build_result(docs[i], metas[i], 1 - dists[i]) for i in selected]


# ── Multi-Query ───────────────────────────────────────────────────────────────

async def _multi_query_pool(
    query: str, query_vector: list, k: int, filters: dict, llm_complete_fn
) -> list[dict]:
    """
    LLM generates 3 query variants → each searched → merged pool returned.
    Returns larger pool (k * 3) for downstream MMR to filter.
    """
    prompt = [
        {"role": "system", "content": MULTI_QUERY_PROMPT["system"]},
        {"role": "user",   "content": MULTI_QUERY_PROMPT["user"].format(query=query)},
    ]
    raw      = await llm_complete_fn(prompt)
    variants = [q.strip() for q in raw.strip().split("\n") if q.strip()][:3]
    variants.append(query)  

    embedder     = EmbeddingService()
    where        = filters if filters else None
    per_query    = max(k, 5)
    all_results: list[dict] = []

    for variant in variants:
        vec = embedder.get_vector(variant)
        res = chroma.collection.query(
            query_embeddings=[vec],
            n_results=per_query,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        for doc, meta, dist in zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            all_results.append(_build_result(doc, meta, 1 - dist))

    all_results.sort(key=lambda x: x["score"], reverse=True)
    return _deduplicate(all_results)


# ── Contextual Compression ────────────────────────────────────────────────────

async def _contextual_compression(
    results: list[dict], query: str, llm_complete_fn
) -> list[dict]:
    """
    LLM trims each passage to only the sentences relevant to the query.
    NOT_RELEVANT passages are dropped entirely.
    """
    compressed = []
    for r in results:
        prompt = [
            {"role": "system", "content": CONTEXTUAL_COMPRESSION_PROMPT["system"]},
            {"role": "user",   "content": CONTEXTUAL_COMPRESSION_PROMPT["user"].format(
                query=query, passage=r["parent_content"]
            )},
        ]
        trimmed = await llm_complete_fn(prompt)
        if trimmed and "NOT_RELEVANT" not in trimmed:
            r["parent_content"] = trimmed.strip()
            compressed.append(r)
    return compressed or results  # fallback: return untrimmed if all marked irrelevant


# ── Self-Query ────────────────────────────────────────────────────────────────

async def _self_query(
    query: str, query_vector: list, k: int, llm_complete_fn
) -> list[dict]:
    """LLM extracts metadata filter → applies to similarity search."""
    prompt = [
        {"role": "system", "content": SELF_QUERY_PROMPT["system"]},
        {"role": "user",   "content": SELF_QUERY_PROMPT["user"].format(query=query)},
    ]
    raw = await llm_complete_fn(prompt)
    try:
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        filters = json.loads(cleaned)
    except Exception:
        logger.warning("self_query: failed to parse filter: %s", raw)
        filters = {}
    return _similarity(query_vector, k, filters)


# ── Hybrid BM25 ───────────────────────────────────────────────────────────────

def _hybrid_bm25(query: str, query_vector: list, k: int, filters: dict) -> list[dict]:
    """Dense vector + BM25 keyword search fused with RRF scoring."""
    where = filters if filters else None

    dense = chroma.collection.query(
        query_embeddings=[query_vector],
        n_results=k * 2,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    tokens       = [t for t in query.lower().split() if len(t) > 3]
    keyword_hits: list[tuple] = []

    for token in tokens[:5]:
        try:
            kw_filter = {"$contains": token}
            if where:
                kw_filter = {"$and": [where, kw_filter]}
            res = chroma.collection.query(
                query_embeddings=[query_vector],
                n_results=k,
                where_document=kw_filter,
                include=["documents", "metadatas", "distances"],
            )
            for doc, meta, dist in zip(
                res["documents"][0], res["metadatas"][0], res["distances"][0]
            ):
                keyword_hits.append((doc, meta, 1 - dist))
        except Exception:
            pass

    rrf_scores: dict[str, float] = {}
    rrf_data:   dict[str, tuple] = {}

    for rank, (doc, meta, dist) in enumerate(zip(
        dense["documents"][0], dense["metadatas"][0], dense["distances"][0]
    )):
        key = f"{meta.get('candidate_id')}_p{meta.get('parent_index')}"
        rrf_scores[key] = rrf_scores.get(key, 0) + _rrf_score(rank)
        rrf_data[key]   = (doc, meta, 1 - dist)

    for rank, (doc, meta, score) in enumerate(keyword_hits):
        key = f"{meta.get('candidate_id')}_p{meta.get('parent_index')}"
        rrf_scores[key] = rrf_scores.get(key, 0) + _rrf_score(rank)
        rrf_data[key]   = (doc, meta, score)

    sorted_keys = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)[:k]
    return [_build_result(rrf_data[k][0], rrf_data[k][1], rrf_scores[k]) for k in sorted_keys]


# ── Ensemble ──────────────────────────────────────────────────────────────────

def _ensemble(query_vector: list, k: int, filters: dict, weights: dict | None = None) -> list[dict]:
    """Weighted merge of similarity + MMR."""
    weights     = weights or {"similarity": 0.5, "mmr": 0.5}
    sim_results = _similarity(query_vector, k, filters)
    mmr_results = _mmr(query_vector, k, filters)

    score_map: dict[str, float] = {}
    data_map:  dict[str, dict]  = {}

    for results, weight in (
        (sim_results, weights.get("similarity", 0.5)),
        (mmr_results, weights.get("mmr", 0.5)),
    ):
        for r in results:
            key = f"{r['candidate_id']}_p{r['parent_index']}"
            score_map[key] = score_map.get(key, 0) + weight * r["score"]
            data_map[key]  = r

    sorted_keys = sorted(score_map, key=lambda x: score_map[x], reverse=True)[:k]
    for key in sorted_keys:
        data_map[key]["score"] = round(score_map[key], 4)
    return [data_map[key] for key in sorted_keys]


# ── Full Pipeline (recommended) ───────────────────────────────────────────────

async def _pipeline(
    query: str, query_vector: list, k: int, filters: dict, llm_complete_fn
) -> list[dict]:
    """
    Full chained pipeline — best results in practice:

    Step 1 — Multi-Query: LLM expands query into 3 variants
             → searches all variants → builds wide candidate pool
             → more recall, catches different phrasings

    Step 2 — MMR from pool: selects k diverse results from the pool
             → no repeated/redundant answers
             → each result covers a different aspect

    Step 3 — Contextual Compression: LLM trims each passage
             → removes irrelevant sentences from parent_content
             → cleaner context injected into final LLM call
    """
    logger.info("pipeline: step 1 — multi-query pool building")
    pool = await _multi_query_pool(query, query_vector, k * 3, filters, llm_complete_fn)

    logger.info("pipeline: step 2 — MMR selection from pool of %d", len(pool))
    diverse = _mmr_from_pool(pool, query_vector, k)

    logger.info("pipeline: step 3 — contextual compression on %d results", len(diverse))
    final = await _contextual_compression(diverse, query, llm_complete_fn)

    logger.info("pipeline: done — %d clean results", len(final))
    return final


# ── Public Interface ──────────────────────────────────────────────────────────

class RAGService:

    @staticmethod
    async def retrieve(
        query: str,
        strategy: RetrievalStrategy = "pipeline",
        k: int = 5,
        filters: dict | None = None,
        llm_complete_fn=None,
        ensemble_weights: dict | None = None,
    ) -> list[dict]:
        embedder     = EmbeddingService()
        query_vector = embedder.get_vector(query)
        filters      = filters or {}

        logger.info("strategy=%s k=%d query='%s'", strategy, k, query[:60])

        if strategy == "pipeline":
            if not llm_complete_fn:
                logger.warning("pipeline: no llm_fn provided, falling back to hybrid_bm25")
                return _hybrid_bm25(query, query_vector, k, filters)
            return await _pipeline(query, query_vector, k, filters, llm_complete_fn)

        if strategy == "similarity":
            return _similarity(query_vector, k, filters)

        if strategy == "mmr":
            return _mmr(query_vector, k, filters)

        if strategy == "multi_query":
            if not llm_complete_fn:
                raise ValueError("multi_query requires llm_complete_fn")
            pool = await _multi_query_pool(query, query_vector, k, filters, llm_complete_fn)
            return pool[:k]

        if strategy == "contextual":
            if not llm_complete_fn:
                raise ValueError("contextual requires llm_complete_fn")
            base = _similarity(query_vector, k * 2, filters)
            return await _contextual_compression(base, query, llm_complete_fn)

        if strategy == "self_query":
            if not llm_complete_fn:
                raise ValueError("self_query requires llm_complete_fn")
            return await _self_query(query, query_vector, k, llm_complete_fn)

        if strategy == "hybrid_bm25":
            return _hybrid_bm25(query, query_vector, k, filters)

        if strategy == "ensemble":
            return _ensemble(query_vector, k, filters, ensemble_weights)

        raise ValueError(f"Unknown strategy: {strategy}")
