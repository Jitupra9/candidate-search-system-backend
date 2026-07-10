import asyncio
import uuid
import json
import logging
from typing import AsyncGenerator

from app.services.rag import default_rag_service, RetrievalStrategy
from app.services.rag.strategies import RetrievalError
from app.llm import caller as llm_caller
from app.llm.providers import get_llm
from app.llm.prompts import SYSTEM_PROMPT, FEW_SHOT_EXAMPLES
from app.core.config import settings

logger = logging.getLogger(__name__)
RETRIEVAL_TIMEOUT_S = getattr(settings, "CHAT_RETRIEVAL_TIMEOUT_S", 20.0)
LLM_FIRST_TOKEN_TIMEOUT_S = getattr(settings, "CHAT_LLM_TIMEOUT_S", 60.0)

GENERIC_RETRIEVAL_ERROR = "Something went wrong while searching. Please try again."
GENERIC_RETRIEVAL_TIMEOUT = "The search is taking longer than expected. Please try again."
GENERIC_LLM_ERROR = "Something went wrong while generating a response. Please try again."
GENERIC_UNEXPECTED_ERROR = "Something unexpected went wrong. Please try again."


def _build_messages(query: str, context_chunks: list[dict]) -> list[dict]:
    context_text = "\n\n---\n\n".join(
        f"[Source {i+1} | Candidate: {r['candidate_id']}]\n{r['content']}"
        for i, r in enumerate(context_chunks)
        if r.get("content")
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *FEW_SHOT_EXAMPLES,
        {"role": "user", "content": f"[CONTEXT]\n{context_text}\n\n[QUESTION]\n{query}"},
    ]


def _format_sources(context_chunks: list[dict]) -> list[dict]:
    return [
        {
            "candidate_id":  r["candidate_id"],
            "content_index": r["content_index"],
            "score":         r["score"],
            "preview":       r["content"][:150] + ("..." if len(r["content"]) > 150 else ""),
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
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        strategy: RetrievalStrategy = "pipeline",
        k: int = 15,
        filters: dict | None = None,
        ensemble_weights: dict | None = None,
    ) -> dict:
        """Non-streaming — returns complete response at once.

        NOTE: debugging/testing entry point only. The real frontend uses
        ask_stream(); this intentionally has lighter error handling since
        it's not on the production request path.
        """
        provider = provider or settings.DEFAULT_PROVIDER
        model    = model    or settings.DEFAULT_MODEL
        chat_id  = str(uuid.uuid4())

        logger.info("ask start — chat_id=%s provider=%s model=%s strategy=%s",
                    chat_id, provider, model, strategy)

        lc_llm = _get_llm(provider, model, temperature)

        context_chunks = await default_rag_service.retrieve(
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
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        strategy: RetrievalStrategy = "pipeline",
        k: int = 5,
        filters: dict | None = None,
        ensemble_weights: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming — the real production path used by the frontend.

        Error handling here is deliberately stricter than ask():
          - Retrieval is bounded by RETRIEVAL_TIMEOUT_S so a hung Chroma/LLM
            dependency degrades to a clean error event instead of an
            indefinitely hanging SSE connection.
          - Every error path sends a generic, user-safe message to the
            client; full exception detail is always logged server-side
            with exc_info=True for debugging.
        """
        provider = provider or settings.DEFAULT_PROVIDER
        model    = model    or settings.DEFAULT_MODEL
        chat_id  = str(uuid.uuid4())

        logger.info("stream start — chat_id=%s provider=%s model=%s strategy=%s k=%d query='%s'",
                    chat_id, provider, model, strategy, k, query[:60])

        def sse(event_type: str, payload: dict) -> str:
            return f"data: {json.dumps({'type': event_type, **payload})}\n\n"

        def sse_error(chat_id: str, user_message: str) -> str:
            # Only the sanitized message and chat_id ever reach the client.
            return sse("error", {"chat_id": chat_id, "message": user_message})

        try:
            lc_llm = _get_llm(provider, model, temperature)

            # -- Retrieval, bounded by a timeout --------------------------------
            try:
                context_chunks = await asyncio.wait_for(
                    default_rag_service.retrieve(
                        query=query, strategy=strategy, k=k,
                        filters=filters, llm=lc_llm,
                        ensemble_weights=ensemble_weights,
                    ),
                    timeout=RETRIEVAL_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "retrieval timed out — chat_id=%s strategy=%s timeout=%.1fs",
                    chat_id, strategy, RETRIEVAL_TIMEOUT_S,
                )
                yield sse_error(chat_id, GENERIC_RETRIEVAL_TIMEOUT)
                return
            except RetrievalError as e:
                # Every strategy's fallback chain was exhausted (e.g. Chroma
                # itself is unreachable). Log full detail, tell the user
                # nothing about internals.
                logger.error(
                    "retrieval failed after all fallbacks — chat_id=%s: %s",
                    chat_id, e, exc_info=True,
                )
                yield sse_error(chat_id, GENERIC_RETRIEVAL_ERROR)
                return

            logger.info("retrieval done — chat_id=%s sources=%d", chat_id, len(context_chunks))

            messages = _build_messages(query, context_chunks)
            sources  = _format_sources(context_chunks)

            yield sse("start", {
                "chat_id": chat_id, "query": query,
                "provider": provider, "model": model, "strategy": strategy,
            })

            token_count = 0
            try:
                stream_iter = llm_caller.stream(messages, provider, model, temperature)
                async for token in stream_iter:
                    token_count += 1
                    yield sse("chunk", {"content": token})
            except Exception as e:
                logger.error(
                    "llm streaming failed mid-response — chat_id=%s tokens_sent=%d: %s",
                    chat_id, token_count, e, exc_info=True,
                )
                # Let the frontend know generation was cut short so it can
                # show "response was cut off" rather than silently stopping.
                yield sse_error(chat_id, GENERIC_LLM_ERROR)
                return

            logger.info("stream complete — chat_id=%s tokens=%d sources=%d",
                        chat_id, token_count, len(sources))

            yield sse("sources", {"source_chunks": sources, "sources_count": len(sources)})
            yield sse("done",    {"chat_id": chat_id})

        except Exception as e:
            # Catch-all for anything not already handled above (e.g. _get_llm
            # failing, an unexpected error building messages). Full detail
            # logged; generic message to the client.
            logger.error("unexpected stream error — chat_id=%s: %s", chat_id, e, exc_info=True)
            yield sse_error(chat_id, GENERIC_UNEXPECTED_ERROR)