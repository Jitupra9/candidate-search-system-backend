"""BM25Cache — content-hashed BM25 index cache.

All state (lock, cached retriever, last hash) lives on the instance.
No module-level globals; tests can inject an isolated instance.

Content-hash invalidation:
  Hashing actual document text + ids (not just count) catches in-place
  edits (same id, changed text) and same-count churn (delete + insert).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import TYPE_CHECKING

from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever

if TYPE_CHECKING:
    from app.services.rag.config import RAGConfig
    from app.services.rag.metrics import Metrics

logger = logging.getLogger(__name__)


class BM25Cache:
    """Owns the BM25 index, its rebuild lock, and content-hash invalidation.

    Args:
        chroma_collection: The raw chromadb Collection object
                           (``chroma.collection``).
        config: ``RAGConfig`` instance for timeout tuning.
        metrics: ``Metrics`` instance for cache hit/miss/rebuild counters.
    """

    def __init__(self, chroma_collection, config: "RAGConfig", metrics: "Metrics") -> None:
        self._collection = chroma_collection
        self._config = config
        self._metrics = metrics
        self._lock = asyncio.Lock()
        self._retriever: BM25Retriever | None = None
        self._hash: str | None = None

    # ── public ────────────────────────────────────────────────────────────────

    async def get_retriever(self) -> BM25Retriever | None:
        """Return a cached BM25Retriever, rebuilding if corpus has changed.

        Returns ``None`` when the collection is empty.
        Serves the stale index on timeout rather than failing the request.
        """
        try:
            async with asyncio.timeout(self._config.bm25_rebuild_lock_timeout_s):
                async with self._lock:
                    return await self._refresh()
        except (asyncio.TimeoutError, TimeoutError):
            logger.error("BM25 index rebuild timed out; serving stale/no index")
            self._metrics.emit("rag.bm25.rebuild_timeout")
            return self._retriever  # serve stale rather than fail the request
        except Exception as e:
            logger.error("BM25 index build failed: %s", e, exc_info=True)
            self._metrics.emit("rag.bm25.build_error")
            return self._retriever

    # ── private ───────────────────────────────────────────────────────────────

    async def _refresh(self) -> BM25Retriever | None:
        """Must be called while holding ``self._lock``."""
        all_docs_data = await asyncio.to_thread(
            self._collection.get, include=["documents", "metadatas"]
        )
        if not all_docs_data.get("documents"):
            return None

        current_hash = self._corpus_hash(all_docs_data)
        if current_hash != self._hash:
            logger.info("Rebuilding BM25 index (content changed)")
            corpus_docs = [
                Document(page_content=text, metadata=meta)
                for text, meta in zip(
                    all_docs_data["documents"], all_docs_data["metadatas"]
                )
            ]
            self._retriever = await asyncio.to_thread(
                BM25Retriever.from_documents, corpus_docs
            )
            self._hash = current_hash
            self._metrics.emit("rag.bm25.cache_rebuild")
            logger.info("BM25 index built with %d documents", len(corpus_docs))
        else:
            self._metrics.emit("rag.bm25.cache_hit")

        return self._retriever

    @staticmethod
    def _corpus_hash(all_docs_data: dict) -> str:
        """MD5 over (id + text) pairs — catches content edits, not just count changes."""
        ids = all_docs_data.get("ids") or []
        docs = all_docs_data.get("documents") or []
        hasher = hashlib.md5()
        for doc_id, text in zip(ids, docs):
            hasher.update(doc_id.encode("utf-8", errors="ignore"))
            hasher.update(b"\x00")
            hasher.update((text or "").encode("utf-8", errors="ignore"))
            hasher.update(b"\x01")
        return hasher.hexdigest()
