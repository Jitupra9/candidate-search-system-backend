"""Backward-compatibility shim.

The RAG service has been refactored into app/services/rag/.
This file re-exports everything so existing imports keep working
without any changes to callers.

Prefer importing directly from the package:
    from app.services.rag import RAGService, RAGConfig, RetrievalError
"""
from app.services.rag import (  # noqa: F401
    RAGService,
    RAGConfig,
    RetrievalError,
    RetrievalStrategy,
    default_rag_service,
)
