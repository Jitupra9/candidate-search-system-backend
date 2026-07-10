"""RAGService — public entry point for all retrieval operations.

Constructor accepts optional injected dependencies; each defaults to a
real production instance when not provided. This makes the class fully
testable (inject fakes) while requiring zero configuration for normal use.

Module-level ``default_rag_service`` is provided for callers that used the
old ``from app.services.rag_service import RAGService`` pattern.
"""
from __future__ import annotations

import logging
from typing import Literal

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.rag.config import RAGConfig
    from app.services.rag.metrics import Metrics
    from app.services.rag.vectorstore_provider import VectorStoreProvider
    from app.services.rag.bm25_cache import BM25Cache
    from app.services.rag.strategies import RetrievalStrategies
logger = logging.getLogger(__name__)

RetrievalStrategy = Literal[
    "pipeline",
    "similarity", "mmr", "multi_query",
    "contextual", "self_query", "hybrid_bm25", "ensemble",
    "hyde",
]


class RAGService:
    

    def __init__(
        self,
        vectorstore_provider: "VectorStoreProvider | None" = None,
        bm25_cache: "BM25Cache | None" = None,
        config: "RAGConfig | None" = None,
        metrics: "Metrics | None" = None,
        strategies: "RetrievalStrategies | None" = None,
    ) -> None:
        # ── resolve dependencies ──────────────────────────────────────────────
        from app.services.rag.config import RAGConfig
        from app.services.rag.metrics import Metrics
        from app.services.rag.vectorstore_provider import VectorStoreProvider
        from app.services.rag.bm25_cache import BM25Cache
        from app.services.rag.strategies import RetrievalStrategies

        self._config: RAGConfig = config or RAGConfig.from_settings()
        self._metrics: Metrics = metrics or Metrics()

        if vectorstore_provider is None:
            from app.core.chroma_client import chroma
            from app.services.Embadding import EmbeddingService
            vectorstore_provider = VectorStoreProvider(
                chroma_client=chroma._client,
                embedding_service=EmbeddingService(),
            )

        if bm25_cache is None:
            from app.core.chroma_client import chroma
            bm25_cache = BM25Cache(
                chroma_collection=chroma.collection,
                config=self._config,
                metrics=self._metrics,
            )

        self._vs_provider: VectorStoreProvider = vectorstore_provider
        self._bm25_cache: BM25Cache = bm25_cache

        self.strategies: RetrievalStrategies = strategies or RetrievalStrategies(
            vectorstore_provider=self._vs_provider,
            bm25_cache=self._bm25_cache,
            config=self._config,
            metrics=self._metrics,
        )

        # ── strategy registry (name → bound method) ───────────────────────────
        self._registry: dict[str, object] = {
            "similarity":  self.strategies.similarity,
            "mmr":         self.strategies.mmr,
            "multi_query": self.strategies.multi_query,
            "contextual":  self.strategies.contextual,
            "self_query":  self.strategies.self_query,
            "hybrid_bm25": self.strategies.hybrid_bm25,
            "ensemble":    self.strategies.ensemble,
            "hyde":        self.strategies.hyde,
            "pipeline":    self.strategies.pipeline,
        }

    # ── public API ────────────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        strategy: RetrievalStrategy = "pipeline",
        k: int = 5,
        filters: dict | None = None,
        llm=None,
        ensemble_weights: dict | None = None,
    ) -> list[dict]:
        filters = filters or {}
        logger.info("strategy=%s k=%d query='%s'", strategy, k, query[:60])

        handler = self._registry.get(strategy)
        if handler is None:
            raise ValueError(f"Unknown strategy: {strategy!r}")

        # Dispatch — each strategy method has a different signature depending
        # on whether it needs llm / weights, so we route explicitly.
        if strategy in ("similarity", "mmr", "hybrid_bm25"):
            return await handler(query, k, filters)  # type: ignore[operator]

        if strategy == "ensemble":
            return await handler(query, k, filters, ensemble_weights)  # type: ignore[operator]

        if strategy in ("multi_query", "contextual", "self_query", "hyde"):
            if not llm:
                raise ValueError(f"{strategy!r} requires llm")
            return await handler(query, k, filters, llm)  # type: ignore[operator]

        if strategy == "pipeline":
            if not llm:
                logger.warning("pipeline: no llm provided, falling back to hybrid_bm25")
                return await self.strategies.hybrid_bm25(query, k, filters)
            return await handler(query, k, filters, llm)  # type: ignore[operator]

        raise ValueError(f"Unknown strategy: {strategy!r}")  # unreachable but safe

    def metrics_snapshot(self) -> dict:
        """Return current in-process metrics snapshot."""
        return self._metrics.snapshot()


# ── module-level default instance (backward-compatible) ──────────────────────
# Existing callers that do:
#   from app.services.rag_service import RAGService
# can now do:
#   from app.services.rag import RAGService
# or use the default instance directly:
#   from app.services.rag.service import default_rag_service
default_rag_service = RAGService()
