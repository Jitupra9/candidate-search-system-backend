import uuid
import json
import logging
from typing import AsyncGenerator
from app.services.rag_service import RAGService, RetrievalStrategy
from app.llm import caller as llm_caller
from app.llm.providers import get_llm
from app.llm.prompts import SYSTEM_PROMPT, FEW_SHOT_EXAMPLES
from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_messages(query: str, context_chunks: list[dict]) -> list[dict]:
    context_text = "\n\n---\n\n".join(
        f"[Source {i+1} | Candidate: {r['candidate_id']}]\n{r['parent_content']}"
        for i, r in enumerate(context_chunks)
        if r.get("parent_content")
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *FEW_SHOT_EXAMPLES,
        {"role": "user", "content": f"[CONTEXT]\n{context_text}\n\n[QUESTION]\n{query}"},
    ]


def _format_sources(context_chunks: list[dict]) -> list[dict]:
    return [
        {
            "candidate_id": r["candidate_id"],
            "parent_index": r["parent_index"],
            "score":        r["score"],
            "preview":      r["child_chunk"][:150] + ("..." if len(r["child_chunk"]) > 150 else ""),
        }
        for r in context_chunks
    ]


def _get_llm(provider: str, model: str, temperature: float):
    """Return a LangChain LLM instance for use in LangChain retrievers."""
    return get_llm(provider=provider, model=model, temperature=temperature)


class ChatService:

    @staticmethod
    async def ask(
        query: str,
        provider: str = None,
        model: str = None,
        temperature: float = 0.7,
        strategy: RetrievalStrategy = "pipeline",
        k: int = 5,
        filters: dict | None = None,
        ensemble_weights: dict | None = None,
    ) -> dict:
        """Non-streaming — returns complete response at once."""
        provider = provider or settings.DEFAULT_PROVIDER
        model    = model    or settings.DEFAULT_MODEL
        chat_id  = str(uuid.uuid4())

        logger.info("ask start — chat_id=%s provider=%s model=%s strategy=%s",
                    chat_id, provider, model, strategy)

        lc_llm = _get_llm(provider, model, temperature)

        context_chunks = await RAGService.retrieve(
            query=query, strategy=strategy, k=k,
            filters=filters, llm=lc_llm,
            ensemble_weights=ensemble_weights,
        )
        messages = _build_messages(query, context_chunks)
        answer   = await llm_caller.complete(messages, provider, model, temperature)
        sources  = _format_sources(context_chunks)

        logger.info("ask complete — chat_id=%s sources=%d", chat_id, len(sources))

        return {
            "chat_id":  chat_id,
            "query":    query,
            "answer":   answer,
            "sources":  sources,
            "provider": provider,
            "model":    model,
            "strategy": strategy,
        }

    @staticmethod
    async def ask_stream(
        query: str,
        provider: str = None,
        model: str = None,
        temperature: float = 0.7,
        strategy: RetrievalStrategy = "pipeline",
        k: int = 5,
        filters: dict | None = None,
        ensemble_weights: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        provider = provider or settings.DEFAULT_PROVIDER
        model    = model    or settings.DEFAULT_MODEL
        chat_id  = str(uuid.uuid4())

        logger.info("stream start — chat_id=%s provider=%s model=%s strategy=%s k=%d query='%s'",
                    chat_id, provider, model, strategy, k, query[:60])

        def sse(event_type: str, payload: dict) -> str:
            return f"data: {json.dumps({'type': event_type, **payload})}\n\n"

        try:
            lc_llm = _get_llm(provider, model, temperature)

            context_chunks = await RAGService.retrieve(
                query=query, strategy=strategy, k=k,
                filters=filters, llm=lc_llm,
                ensemble_weights=ensemble_weights,
            )
            logger.info("retrieval done — chat_id=%s sources=%d", chat_id, len(context_chunks))

            messages = _build_messages(query, context_chunks)
            sources  = _format_sources(context_chunks)

            yield sse("start", {
                "chat_id": chat_id, "query": query,
                "provider": provider, "model": model, "strategy": strategy,
            })

            token_count = 0
            async for token in llm_caller.stream(messages, provider, model, temperature):
                token_count += 1
                yield sse("chunk", {"content": token})

            logger.info("stream complete — chat_id=%s tokens=%d sources=%d",
                        chat_id, token_count, len(sources))

            yield sse("sources", {"source_chunks": sources, "sources_count": len(sources)})
            yield sse("done",    {"chat_id": chat_id})

        except Exception as e:
            logger.error("stream error — chat_id=%s error=%s", chat_id, e, exc_info=True)
            yield sse("error", {"message": str(e)})
