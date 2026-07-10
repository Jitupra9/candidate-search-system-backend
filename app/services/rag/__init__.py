"""app.services.rag — RAG retrieval package.

Public surface::

    from app.services.rag import RAGService, RAGConfig, RetrievalError
    from app.services.rag import RetrievalStrategy          # type alias
    from app.services.rag.service import default_rag_service
"""
from app.services.rag.config import RAGConfig
from app.services.rag.strategies import RetrievalError
from app.services.rag.service import RAGService, RetrievalStrategy, default_rag_service

__all__ = [
    "RAGService",
    "RAGConfig",
    "RetrievalError",
    "RetrievalStrategy",
    "default_rag_service",
]
