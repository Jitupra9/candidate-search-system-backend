"""
RAG Service — LangChain Retriever Strategies
=============================================

Strategies:
  similarity    → Top-k cosine similarity
  mmr           → Max Marginal Relevance
  multi_query   → LLM expands query into variants, merges recall
  contextual    → LLM trims irrelevant passage parts (ContextualCompressionRetriever)
  self_query    → LLM extracts metadata filter from natural language (SelfQueryRetriever)
  hybrid_bm25   → BM25 keyword + dense vector, RRF fusion (EnsembleRetriever)
  ensemble      → Weighted merge of similarity + MMR
  pipeline      → multi_query → MMR → contextual compression (recommended)

Parent-Child Pattern:
  child chunk    → small text embedded in ChromaDB (fast vector search)
  parent_content → full passage stored in metadata
  search finds child → parent_content already in metadata → inject into LLM
"""
import logging
from typing import Literal
import numpy as np
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_classic.retrievers import ContextualCompressionRetriever,EnsembleRetriever
from langchain_classic.retrievers.multi_query import MultiQueryRetriever
from langchain_classic.retrievers.document_compressors import LLMChainExtractor
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores.utils import maximal_marginal_relevance
from app.core.chroma_client import chroma
from app.core.config import settings
from app.services.Embadding import EmbeddingService

logger = logging.getLogger(__name__)

RetrievalStrategy = Literal[
    "pipeline",
    "similarity", "mmr", "multi_query",
    "contextual", "self_query", "hybrid_bm25", "ensemble",
]


def _get_vectorstore(filters: dict | None = None) -> Chroma:
    embedder = EmbeddingService()
    return Chroma(
        client=chroma._client,
        collection_name="candidate_chunks",
        embedding_function=embedder.embeddings,
        collection_metadata={"hnsw:space": "cosine"},
    )


def _doc_to_result(doc: Document, score: float = 1.0) -> dict:
    meta = doc.metadata
    return {
        "child_chunk":    doc.page_content,
        "parent_content": meta.get("parent_content") or doc.page_content,
        "candidate_id":   meta.get("candidate_id", ""),
        "parent_index":   meta.get("parent_index", -1),
        "file_type":      meta.get("file_type", ""),
        "score":          round(score, 4),
    }


def _deduplicate(results: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for r in results:
        key = (r["candidate_id"], r["parent_index"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def _chroma_filter(filters: dict | None) -> dict | None:
    return filters if filters else None


# ── Similarity ────────────────────────────────────────────────────────────────

def _similarity(query: str, k: int, filters: dict) -> list[dict]:
    vs = _get_vectorstore()
    docs_scores = vs.similarity_search_with_relevance_scores(
        query, k=k, filter=_chroma_filter(filters)
    )
    return _deduplicate([_doc_to_result(doc, score) for doc, score in docs_scores])


# ── MMR ───────────────────────────────────────────────────────────────────────

def _mmr(query: str, k: int, filters: dict) -> list[dict]:
    vs = _get_vectorstore()
    retriever = vs.as_retriever(
        search_type="mmr",
        search_kwargs={"k": k, "fetch_k": min(k * 4, 50), "filter": _chroma_filter(filters)},
    )
    docs = retriever.invoke(query)
    return _deduplicate([_doc_to_result(doc) for doc in docs])


# ── Multi-Query ───────────────────────────────────────────────────────────────

async def _multi_query(query: str, k: int, filters: dict, llm) -> list[dict]:
    vs = _get_vectorstore()
    base_retriever = vs.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k, "filter": _chroma_filter(filters)},
    )
    retriever = MultiQueryRetriever.from_llm(retriever=base_retriever, llm=llm)
    docs = await retriever.ainvoke(query)
    return _deduplicate([_doc_to_result(doc) for doc in docs])[:k]


# ── Contextual Compression ────────────────────────────────────────────────────

async def _contextual(query: str, k: int, filters: dict, llm) -> list[dict]:
    vs = _get_vectorstore()
    base_retriever = vs.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k * 2, "filter": _chroma_filter(filters)},
    )
    compressor = LLMChainExtractor.from_llm(llm)
    retriever = ContextualCompressionRetriever(
        base_compressor=compressor, base_retriever=base_retriever
    )
    docs = await retriever.ainvoke(query)
    return _deduplicate([_doc_to_result(doc) for doc in docs])[:k]


# ── Self-Query ────────────────────────────────────────────────────────────────

async def _self_query(query: str, k: int, llm) -> list[dict]:
    """
    Uses MultiQueryRetriever as a practical self-query alternative —
    SelfQueryRetriever requires strict metadata field definitions upfront.
    LLM generates query variants that naturally encode filter intent.
    """
    vs = _get_vectorstore()
    base_retriever = vs.as_retriever(search_kwargs={"k": k})
    retriever = MultiQueryRetriever.from_llm(retriever=base_retriever, llm=llm)
    docs = await retriever.ainvoke(query)
    return _deduplicate([_doc_to_result(doc) for doc in docs])[:k]


# ── Hybrid BM25 ───────────────────────────────────────────────────────────────

def _hybrid_bm25(query: str, k: int, filters: dict) -> list[dict]:
    """EnsembleRetriever: BM25 + dense vector with RRF fusion."""
    vs = _get_vectorstore()

    # Fetch a broad set of docs from Chroma to build BM25 corpus
    all_docs_data = chroma.collection.get(include=["documents", "metadatas"])
    corpus_docs = [
        Document(page_content=text, metadata=meta)
        for text, meta in zip(all_docs_data["documents"], all_docs_data["metadatas"])
    ]

    if not corpus_docs:
        return _similarity(query, k, filters)

    bm25_retriever = BM25Retriever.from_documents(corpus_docs, k=k)
    dense_retriever = vs.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k, "filter": _chroma_filter(filters)},
    )
    ensemble = EnsembleRetriever(
        retrievers=[bm25_retriever, dense_retriever],
        weights=[0.4, 0.6],
    )
    docs = ensemble.invoke(query)
    return _deduplicate([_doc_to_result(doc) for doc in docs])[:k]


# ── Ensemble (similarity + MMR) ───────────────────────────────────────────────

def _ensemble(query: str, k: int, filters: dict, weights: dict | None = None) -> list[dict]:
    """EnsembleRetriever: weighted merge of similarity + MMR."""
    weights = weights or {"similarity": 0.5, "mmr": 0.5}
    vs = _get_vectorstore()

    sim_retriever = vs.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k, "filter": _chroma_filter(filters)},
    )
    mmr_retriever = vs.as_retriever(
        search_type="mmr",
        search_kwargs={"k": k, "fetch_k": min(k * 4, 50), "filter": _chroma_filter(filters)},
    )
    ensemble = EnsembleRetriever(
        retrievers=[sim_retriever, mmr_retriever],
        weights=[weights.get("similarity", 0.5), weights.get("mmr", 0.5)],
    )
    docs = ensemble.invoke(query)
    return _deduplicate([_doc_to_result(doc) for doc in docs])[:k]


# ── Full Pipeline (recommended) ───────────────────────────────────────────────

async def _pipeline(query: str, k: int, filters: dict, llm) -> list[dict]:
    """
    multi_query → MMR → contextual compression
    Best recall + diversity + clean context.
    """
    logger.info("pipeline: step 1 — multi-query")
    pool = await _multi_query(query, k * 3, filters, llm)
    if not pool:
        return []

    logger.info("pipeline: step 2 — MMR from pool of %d", len(pool))
    # Re-rank pool with MMR via vectorstore
    embedder = EmbeddingService()
    query_embedding = embedder.embeddings.embed_query(query)
    doc_embeddings = embedder.embeddings.embed_documents(
        [r["child_chunk"] for r in pool]
    )
    
    selected = maximal_marginal_relevance(
        query_embedding=np.array(query_embedding),
        embedding_list=np.array(doc_embeddings),
        lambda_mult=0.5,
        k=k,
    )
    diverse = [pool[i] for i in selected]
    diverse = _deduplicate(diverse)

    logger.info("pipeline: step 3 — contextual compression on %d results", len(diverse))
    compressor = LLMChainExtractor.from_llm(llm)
    compressed = []
    for r in diverse:
        doc = Document(page_content=r["parent_content"], metadata={})
        result = await compressor.acompress_documents([doc], query)
        if result:
            r["parent_content"] = result[0].page_content
            compressed.append(r)

    final = compressed or diverse
    logger.info("pipeline: done — %d results", len(final))
    return final


# ── Public Interface ──────────────────────────────────────────────────────────

class RAGService:

    @staticmethod
    async def retrieve(
        query: str,
        strategy: RetrievalStrategy = "pipeline",
        k: int = 5,
        filters: dict | None = None,
        llm=None,                    
        ensemble_weights: dict | None = None,
    ) -> list[dict]:
        filters = filters or {}
        logger.info("strategy=%s k=%d query='%s'", strategy, k, query[:60])

        if strategy == "pipeline":
            if not llm:
                logger.warning("pipeline: no llm provided, falling back to hybrid_bm25")
                return _hybrid_bm25(query, k, filters)
            return await _pipeline(query, k, filters, llm)

        if strategy == "similarity":
            return _similarity(query, k, filters)

        if strategy == "mmr":
            return _mmr(query, k, filters)

        if strategy == "multi_query":
            if not llm:
                raise ValueError("multi_query requires llm")
            return await _multi_query(query, k, filters, llm)

        if strategy == "contextual":
            if not llm:
                raise ValueError("contextual requires llm")
            return await _contextual(query, k, filters, llm)

        if strategy == "self_query":
            if not llm:
                raise ValueError("self_query requires llm")
            return await _self_query(query, k, llm)

        if strategy == "hybrid_bm25":
            return _hybrid_bm25(query, k, filters)

        if strategy == "ensemble":
            return _ensemble(query, k, filters, ensemble_weights)

        raise ValueError(f"Unknown strategy: {strategy}")
