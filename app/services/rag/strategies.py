"""RetrievalStrategies — one async method per retrieval strategy.

All external dependencies are injected via __init__; nothing is imported
or instantiated inside method bodies.

Strategies
----------
similarity    Top-k cosine similarity (base fallback target)
mmr           Max Marginal Relevance
multi_query   LLM expands query into variants, merges recall
contextual    LLM trims irrelevant passage parts
self_query    Metadata-aware retrieval via query-variant expansion
              (NOTE: practical stand-in — not LangChain's SelfQueryRetriever,
              which requires strict metadata schemas defined upfront)
hybrid_bm25   BM25 keyword + dense vector, RRF fusion (EnsembleRetriever)
ensemble      Weighted merge of similarity + MMR
hyde          Hypothetical Document Embeddings (opt-in, not in pipeline)
pipeline      Adaptive flow (recommended):
                similarity → confidence check
                  high confidence → MMR
                  low confidence  → multi_query → MMR
                → long-context check
                  short → return directly
                  long  → contextual compression (per-doc gated)
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import numpy as np
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_classic.retrievers import ContextualCompressionRetriever, EnsembleRetriever
from langchain_classic.retrievers.multi_query import MultiQueryRetriever
from langchain_classic.retrievers.document_compressors import LLMChainExtractor
from langchain_community.vectorstores.utils import maximal_marginal_relevance

if TYPE_CHECKING:
    from app.services.rag.config import RAGConfig
    from app.services.rag.metrics import Metrics
    from app.services.rag.vectorstore_provider import VectorStoreProvider
    from app.services.rag.bm25_cache import BM25Cache

logger = logging.getLogger(__name__)


class RetrievalError(RuntimeError):
    """Raised when a strategy fails after exhausting all fallbacks."""


class RetrievalStrategies:
    """All retrieval strategy implementations.

    Args:
        vectorstore_provider: Provides the lazy-cached Chroma vectorstore.
        bm25_cache: Provides the lazy-cached BM25 retriever.
        config: Frozen RAGConfig with all tunable knobs.
        metrics: Metrics instance for counters and latency.
    """

    def __init__(
        self,
        vectorstore_provider: "VectorStoreProvider",
        bm25_cache: "BM25Cache",
        config: "RAGConfig",
        metrics: "Metrics",
    ) -> None:
        self._vs_provider = vectorstore_provider
        self._bm25_cache = bm25_cache
        self._config = config
        self._metrics = metrics

    # ── private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _doc_to_result(doc: Document, score: float = 1.0) -> dict:
        meta = doc.metadata
        return {
            "content":       meta.get("content") or doc.page_content,
            "candidate_id":  meta.get("candidate_id", ""),
            "content_index": meta.get("content_index", -1),
            "file_type":     meta.get("file_type", ""),
            "score":         round(score, 4),
        }

    @staticmethod
    def _deduplicate(results: list[dict]) -> list[dict]:
        seen: set[tuple] = set()
        unique: list[dict] = []
        for r in results:
            key = (r["candidate_id"], r["content_index"])
            if key not in seen:
                seen.add(key)
                unique.append(r)
        return unique

    @staticmethod
    def _chroma_filter(filters: dict | None) -> dict | None:
        return filters if filters else None

    def _is_simple_query(self, query: str) -> bool:
        """Heuristic (no LLM call) to catch short, direct factual questions.

        Deliberately conservative: false negatives (treating a simple query as
        complex) just cost an extra LLM call. False positives (treating a
        complex query as simple) skip useful expansion, so the word-count bar
        is kept low and prefix list narrow.
        """
        q = query.strip().lower()
        if not q:
            return False
        word_count = len(q.split())
        if word_count <= self._config.simple_query_max_words:
            return True
        if any(q.startswith(p) for p in self._config.simple_query_prefixes):
            return word_count <= self._config.simple_query_max_words + 4
        return False

    def _estimate_confidence(self, results: list[dict]) -> float:
        """Average relevance score of the top-N similarity results.

        Averaging the top few rather than just the single top hit avoids one
        lucky high-scoring outlier making a genuinely ambiguous query look
        "confident".
        """
        if not results:
            return 0.0
        top_n = results[: self._config.confidence_top_n]
        scores = [r.get("score", 0.0) for r in top_n]
        return sum(scores) / len(scores) if scores else 0.0

    async def _mmr_rerank(self, query: str, pool: list[dict], k: int) -> list[dict]:
        """Re-rank an arbitrary result pool for diversity using MMR.

        Shared by both the high-confidence and low-confidence branches of the
        pipeline so MMR logic lives in one place.
        """
        if not pool:
            return []
        try:
            embedder = self._vs_provider.embedding_service
            query_embedding = await embedder.embeddings.aembed_query(query)
            doc_embeddings = await embedder.embeddings.aembed_documents(
                [r["content"] for r in pool]
            )
            selected = maximal_marginal_relevance(
                query_embedding=np.array(query_embedding),
                embedding_list=np.array(doc_embeddings),
                lambda_mult=0.5,
                k=k,
            )
            return self._deduplicate([pool[i] for i in selected])
        except Exception as e:
            logger.warning("pipeline: MMR re-rank failed (%s), using raw pool", e)
            self._metrics.emit("rag.pipeline.mmr_stage_failure")
            return self._deduplicate(pool)[:k]

    async def _compress_parallel(
        self, diverse: list[dict], query: str, compressor
    ) -> list[dict]:
        """Compress each doc concurrently; failures per-doc are swallowed."""
        if not diverse:
            return []

        async def compress_single(doc_dict: dict) -> dict | None:
            doc = Document(page_content=doc_dict["content"], metadata={})
            try:
                result = await compressor.acompress_documents([doc], query)
            except Exception as e:
                logger.warning("compression failed for one doc: %s", e)
                self._metrics.emit("rag.pipeline.compression_doc_failure")
                return None
            if result:
                doc_dict["content"] = result[0].page_content
                return doc_dict
            return None

        raw_results = await asyncio.gather(
            *(compress_single(r) for r in diverse), return_exceptions=True
        )
        out: list[dict] = []
        for r in raw_results:
            if isinstance(r, Exception):
                logger.warning("compression task raised: %s", r)
                continue
            if r is not None:
                out.append(r)
        return out

    # ── strategies ────────────────────────────────────────────────────────────

    async def similarity(self, query: str, k: int, filters: dict) -> list[dict]:
        """Top-k cosine similarity — base fallback target for other strategies."""
        async with self._metrics.timed("similarity"):
            try:
                vs: Chroma = await self._vs_provider.get()
                docs_scores = await vs.asimilarity_search_with_relevance_scores(
                    query, k=k, filter=self._chroma_filter(filters)
                )
                return self._deduplicate(
                    [self._doc_to_result(doc, score) for doc, score in docs_scores]
                )
            except Exception as e:
                logger.error("similarity search failed: %s", e, exc_info=True)
                raise RetrievalError(f"similarity search failed: {e}") from e

    async def mmr(self, query: str, k: int, filters: dict) -> list[dict]:
        """Max Marginal Relevance — diverse results, reduces redundancy."""
        async with self._metrics.timed("mmr"):
            try:
                vs: Chroma = await self._vs_provider.get()
                fetch_k = min(
                    k * self._config.mmr_fetch_k_multiplier,
                    self._config.mmr_fetch_k_cap,
                )
                retriever = vs.as_retriever(
                    search_type="mmr",
                    search_kwargs={
                        "k": k,
                        "fetch_k": fetch_k,
                        "filter": self._chroma_filter(filters),
                    },
                )
                docs = await retriever.ainvoke(query)
                return self._deduplicate([self._doc_to_result(doc) for doc in docs])
            except Exception as e:
                logger.warning("mmr failed (%s), falling back to similarity", e)
                self._metrics.emit("rag.mmr.fallback")
                return await self.similarity(query, k, filters)

    async def multi_query(self, query: str, k: int, filters: dict, llm) -> list[dict]:
        """LLM generates query variants → merged recall pool."""
        async with self._metrics.timed("multi_query"):
            try:
                vs: Chroma = await self._vs_provider.get()
                base_retriever = vs.as_retriever(
                    search_type="similarity",
                    search_kwargs={"k": k, "filter": self._chroma_filter(filters)},
                )
                retriever = MultiQueryRetriever.from_llm(
                    retriever=base_retriever, llm=llm
                )
                docs = await retriever.ainvoke(query)
                return self._deduplicate([self._doc_to_result(doc) for doc in docs])[:k]
            except Exception as e:
                logger.warning("multi_query failed (%s), falling back to similarity", e)
                self._metrics.emit("rag.multi_query.fallback")
                return await self.similarity(query, k, filters)

    async def contextual(self, query: str, k: int, filters: dict, llm) -> list[dict]:
        """LLM trims irrelevant passage parts via ContextualCompressionRetriever."""
        async with self._metrics.timed("contextual"):
            try:
                vs: Chroma = await self._vs_provider.get()
                base_retriever = vs.as_retriever(
                    search_type="similarity",
                    search_kwargs={
                        "k": k * self._config.contextual_overfetch_multiplier,
                        "filter": self._chroma_filter(filters),
                    },
                )
                compressor = LLMChainExtractor.from_llm(llm)
                retriever = ContextualCompressionRetriever(
                    base_compressor=compressor, base_retriever=base_retriever
                )
                docs = await retriever.ainvoke(query)
                results = self._deduplicate(
                    [self._doc_to_result(doc) for doc in docs]
                )[:k]
                if results:
                    return results
                logger.warning("contextual compression returned nothing, falling back")
                self._metrics.emit("rag.contextual.fallback")
                return await self.similarity(query, k, filters)
            except Exception as e:
                logger.warning("contextual failed (%s), falling back to similarity", e)
                self._metrics.emit("rag.contextual.fallback")
                return await self.similarity(query, k, filters)

    async def self_query(self, query: str, k: int, filters: dict, llm) -> list[dict]:
        """Metadata-aware retrieval via query-variant expansion.

        NOTE: This is a practical stand-in for LangChain's SelfQueryRetriever,
        which requires strict metadata field definitions upfront. MultiQuery
        expansion naturally encodes filter intent without schema definitions.
        """
        async with self._metrics.timed("self_query"):
            try:
                vs: Chroma = await self._vs_provider.get()
                base_retriever = vs.as_retriever(
                    search_kwargs={"k": k, "filter": self._chroma_filter(filters)}
                )
                retriever = MultiQueryRetriever.from_llm(
                    retriever=base_retriever, llm=llm
                )
                docs = await retriever.ainvoke(query)
                return self._deduplicate([self._doc_to_result(doc) for doc in docs])[:k]
            except Exception as e:
                logger.warning("self_query failed (%s), falling back to similarity", e)
                self._metrics.emit("rag.self_query.fallback")
                return await self.similarity(query, k, filters)

    async def hybrid_bm25(self, query: str, k: int, filters: dict) -> list[dict]:
        """BM25 keyword + dense vector fused with RRF via EnsembleRetriever."""
        async with self._metrics.timed("hybrid_bm25"):
            bm25_retriever = await self._bm25_cache.get_retriever()

            if bm25_retriever is None:
                logger.warning("No BM25 index available, falling back to similarity")
                self._metrics.emit("rag.hybrid_bm25.fallback")
                return await self.similarity(query, k, filters)

            try:
                bm25_local = bm25_retriever.copy(update={"k": k})
                vs: Chroma = await self._vs_provider.get()
                dense_retriever = vs.as_retriever(
                    search_type="similarity",
                    search_kwargs={"k": k, "filter": self._chroma_filter(filters)},
                )
                ensemble = EnsembleRetriever(
                    retrievers=[bm25_local, dense_retriever],
                    weights=[
                        self._config.hybrid_bm25_weight,
                        self._config.hybrid_dense_weight,
                    ],
                )
                docs = await ensemble.ainvoke(query)
                return self._deduplicate(
                    [self._doc_to_result(doc) for doc in docs]
                )[:k]
            except Exception as e:
                logger.warning(
                    "hybrid_bm25 ensemble failed (%s), falling back to similarity", e
                )
                self._metrics.emit("rag.hybrid_bm25.fallback")
                return await self.similarity(query, k, filters)

    async def ensemble(
        self, query: str, k: int, filters: dict, weights: dict | None = None
    ) -> list[dict]:
        """Weighted merge of similarity + MMR via EnsembleRetriever."""
        async with self._metrics.timed("ensemble"):
            weights = weights or {
                "similarity": self._config.ensemble_similarity_weight,
                "mmr": self._config.ensemble_mmr_weight,
            }
            try:
                vs: Chroma = await self._vs_provider.get()
                fetch_k = min(
                    k * self._config.mmr_fetch_k_multiplier,
                    self._config.mmr_fetch_k_cap,
                )
                sim_retriever = vs.as_retriever(
                    search_type="similarity",
                    search_kwargs={"k": k, "filter": self._chroma_filter(filters)},
                )
                mmr_retriever = vs.as_retriever(
                    search_type="mmr",
                    search_kwargs={
                        "k": k,
                        "fetch_k": fetch_k,
                        "filter": self._chroma_filter(filters),
                    },
                )
                ens = EnsembleRetriever(
                    retrievers=[sim_retriever, mmr_retriever],
                    weights=[
                        weights.get("similarity", 0.5),
                        weights.get("mmr", 0.5),
                    ],
                )
                docs = await ens.ainvoke(query)
                return self._deduplicate(
                    [self._doc_to_result(doc) for doc in docs]
                )[:k]
            except Exception as e:
                logger.warning("ensemble failed (%s), falling back to similarity", e)
                self._metrics.emit("rag.ensemble.fallback")
                return await self.similarity(query, k, filters)

    async def hyde(self, query: str, k: int, filters: dict, llm) -> list[dict]:
        """Hypothetical Document Embeddings — opt-in, not part of default pipeline."""
        async with self._metrics.timed("hyde"):
            try:
                hypothetical_doc = await self._generate_hypothetical_document(
                    query, llm
                )
                logger.info(
                    "hyde: generated hypothetical doc (%d chars)", len(hypothetical_doc)
                )
                vs: Chroma = await self._vs_provider.get()
                docs = await vs.asimilarity_search(
                    hypothetical_doc, k=k, filter=self._chroma_filter(filters)
                )
                return self._deduplicate(
                    [self._doc_to_result(doc) for doc in docs]
                )[:k]
            except Exception as e:
                logger.warning("hyde failed (%s), falling back to similarity", e)
                self._metrics.emit("rag.hyde.fallback")
                return await self.similarity(query, k, filters)

    async def pipeline(self, query: str, k: int, filters: dict, llm) -> list[dict]:
        """Adaptive pipeline (recommended default).

        Flow::

            similarity search → confidence check
                high confidence → MMR re-rank
                low confidence  → multi_query → MMR re-rank
            → long-context check
                short context → return directly
                long context  → contextual compression
                                (per-doc gated by compression_min_chars)

        Cost-saving short-circuits (each independently metered):
          - Simple/direct queries skip straight to similarity (0 LLM calls).
          - High-confidence similarity results skip multi_query (1 fewer LLM call).
          - Short combined context skips compression entirely (k fewer LLM calls).
          - Compression only runs on individual docs exceeding compression_min_chars.
        """
        async with self._metrics.timed("pipeline"):
            if self._is_simple_query(query):
                logger.info(
                    "pipeline: '%s' classified as simple query, skipping expansion",
                    query[:60],
                )
                self._metrics.emit("rag.pipeline.simple_query_shortcut")
                return await self.similarity(query, k, filters)

            # Step 1: similarity search + confidence check
            try:
                initial = await self.similarity(query, k, filters)
            except RetrievalError as e:
                logger.warning(
                    "pipeline: initial similarity failed (%s), treating as low confidence", e
                )
                self._metrics.emit("rag.pipeline.initial_similarity_failure")
                initial = []

            confidence = self._estimate_confidence(initial)
            high_confidence = confidence >= self._config.confidence_threshold

            if high_confidence:
                logger.info(
                    "pipeline: high confidence (%.2f), skipping multi_query", confidence
                )
                self._metrics.emit("rag.pipeline.high_confidence_path")
                pool = initial
            else:
                logger.info(
                    "pipeline: low confidence (%.2f), expanding via multi_query", confidence
                )
                self._metrics.emit("rag.pipeline.low_confidence_path")
                pool = await self.multi_query(
                    query, k * self._config.pipeline_pool_multiplier, filters, llm
                )
                if not pool:
                    logger.warning(
                        "pipeline: empty pool from multi_query, falling back to initial"
                    )
                    self._metrics.emit("rag.pipeline.fallback")
                    pool = initial

            if not pool:
                return []

            # Step 2: MMR re-rank (both branches converge here)
            diverse = await self._mmr_rerank(query, pool, k)
            if not diverse:
                return []

            # Step 3: long-context check
            total_chars = sum(len(r.get("content", "")) for r in diverse)
            if total_chars <= self._config.long_context_chars_threshold:
                logger.info(
                    "pipeline: combined context %d chars <= threshold %d, skipping compression",
                    total_chars,
                    self._config.long_context_chars_threshold,
                )
                self._metrics.emit("rag.pipeline.compression_skipped_short_context")
                return diverse

            self._metrics.emit("rag.pipeline.long_context_path")

            # Per-document gating within the compression stage
            to_compress = [
                r
                for r in diverse
                if len(r.get("content", "")) > self._config.compression_min_chars
            ]
            already_short = [r for r in diverse if r not in to_compress]

            if not to_compress:
                self._metrics.emit("rag.pipeline.compression_skipped_short_chunks")
                return diverse

            try:
                compressor = LLMChainExtractor.from_llm(llm)
                compressed = await self._compress_parallel(to_compress, query, compressor)
                self._metrics.emit(
                    "rag.pipeline.compression_ran_on_n", len(to_compress), kind="counter"
                )
            except Exception as e:
                logger.warning(
                    "pipeline: compression stage failed (%s), using uncompressed", e
                )
                self._metrics.emit("rag.pipeline.compression_stage_failure")
                compressed = []

            return (compressed or to_compress) + already_short

    # ── HyDE helper (private) ─────────────────────────────────────────────────

    @staticmethod
    async def _generate_hypothetical_document(query: str, llm) -> str:
        prompt = (
            "You are a helpful assistant. Write a concise, factual document "
            "that thoroughly answers the following question.\n\n"
            f"Question: {query}\n\n"
            "Write a document that contains the answer in a clear, structured format. "
            "Make it sound like a real encyclopedia entry."
        )
        response = await llm.ainvoke(prompt)
        return response.content if hasattr(response, "content") else str(response)
