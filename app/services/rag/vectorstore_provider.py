"""VectorStoreProvider — lazy, per-instance Chroma + embedder cache.

No module-level singletons. Each instance owns its own lock and cached
vectorstore so tests can inject isolated instances without shared state.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from langchain_chroma import Chroma

if TYPE_CHECKING:
    from app.services.Embadding import EmbeddingService

logger = logging.getLogger(__name__)


class VectorStoreProvider:
    """Lazily builds and caches one Chroma vectorstore per instance.

    Constructor parameters are the *already-constructed* dependencies so
    nothing is imported or instantiated inside method bodies.

    Args:
        chroma_client: The raw chromadb HttpClient (``chroma._client``).
        embedding_service: An ``EmbeddingService`` instance.
        collection_name: ChromaDB collection to use.
    """

    def __init__(
        self,
        chroma_client,
        embedding_service: "EmbeddingService",
        collection_name: str = "candidate_chunks",
    ) -> None:
        self._chroma_client = chroma_client
        self._embedding_service = embedding_service
        self._collection_name = collection_name
        self._vectorstore: Chroma | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> Chroma:
        """Return the cached Chroma instance, building it on first call."""
        if self._vectorstore is not None:
            return self._vectorstore
        async with self._lock:
            if self._vectorstore is None:
                logger.info("VectorStoreProvider: building Chroma vectorstore")
                self._vectorstore = Chroma(
                    client=self._chroma_client,
                    collection_name=self._collection_name,
                    embedding_function=self._embedding_service.embeddings,
                    collection_metadata={"hnsw:space": "cosine"},
                )
        return self._vectorstore

    @property
    def embedding_service(self) -> "EmbeddingService":
        return self._embedding_service
