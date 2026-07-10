"""RAGConfig — all tunable knobs for the RAG pipeline.

Frozen dataclass so instances are safe to share across threads/tasks.
`from_settings()` pulls overrides from app settings; falls back to
coded defaults so the app works with a minimal .env.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # kept for future type-only imports


@dataclass(frozen=True)
class RAGConfig:
    """Tunable knobs, overridable from settings/env without touching code."""

    mmr_fetch_k_multiplier: int = 4
    mmr_fetch_k_cap: int = 50
    pipeline_pool_multiplier: int = 3
    hybrid_bm25_weight: float = 0.4
    hybrid_dense_weight: float = 0.6
    ensemble_similarity_weight: float = 0.5
    ensemble_mmr_weight: float = 0.5
    contextual_overfetch_multiplier: int = 2
    bm25_rebuild_lock_timeout_s: float = 30.0

    # simple/direct query short-circuit
    simple_query_max_words: int = 6
    simple_query_prefixes: tuple = (
        "what is", "who is", "when is", "where is", "define",
        "what's", "who's", "capital of", "meaning of",
    )

    # content-length-gated contextual compression
    compression_min_chars: int = 500

    # confidence-gated retrieval
    confidence_threshold: float = 0.75
    confidence_top_n: int = 3

    # long-context-gated compression
    long_context_chars_threshold: int = 4000

    @classmethod
    def from_settings(cls) -> "RAGConfig":
        """Pull overrides from app settings; fall back to dataclass defaults."""
        from app.core.config import settings  # imported here to avoid module-level coupling

        return cls(
            mmr_fetch_k_multiplier=getattr(settings, "RAG_MMR_FETCH_K_MULTIPLIER", 4),
            mmr_fetch_k_cap=getattr(settings, "RAG_MMR_FETCH_K_CAP", 50),
            pipeline_pool_multiplier=getattr(settings, "RAG_PIPELINE_POOL_MULTIPLIER", 3),
            hybrid_bm25_weight=getattr(settings, "RAG_HYBRID_BM25_WEIGHT", 0.4),
            hybrid_dense_weight=getattr(settings, "RAG_HYBRID_DENSE_WEIGHT", 0.6),
            simple_query_max_words=getattr(settings, "RAG_SIMPLE_QUERY_MAX_WORDS", 6),
            compression_min_chars=getattr(settings, "RAG_COMPRESSION_MIN_CHARS", 500),
            confidence_threshold=getattr(settings, "RAG_CONFIDENCE_THRESHOLD", 0.75),
            confidence_top_n=getattr(settings, "RAG_CONFIDENCE_TOP_N", 3),
            long_context_chars_threshold=getattr(settings, "RAG_LONG_CONTEXT_CHARS", 4000),
            ensemble_similarity_weight=getattr(settings, "RAG_ENSEMBLE_SIM_WEIGHT", 0.5),
            ensemble_mmr_weight=getattr(settings, "RAG_ENSEMBLE_MMR_WEIGHT", 0.5),
            contextual_overfetch_multiplier=getattr(settings, "RAG_CONTEXTUAL_OVERFETCH", 2),
        )
