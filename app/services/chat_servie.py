import uuid
import json
import logging
from typing import AsyncGenerator
from app.services.rag_service import RAGService, RetrievalStrategy
from app.llm import caller as llm
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


class ChatService:

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
        """
        Streaming SSE pipeline.
        Event sequence:
          start   → frontend inits chat bubble
          chunk   → one per LLM token, frontend appends to bubble
          sources → retrieved context cards shown below answer
          done    → frontend marks message complete
          error   → only on failure
        """
        chat_id = str(uuid.uuid4())

        def sse(event_type: str, payload: dict) -> str:
            return f"data: {json.dumps({'type': event_type, **payload})}\n\n"

        try:
            async def llm_fn(messages):
                return await llm.complete(messages, provider, model, temperature)

            context_chunks = await RAGService.retrieve(
                query=query, strategy=strategy, k=k,
                filters=filters, llm_complete_fn=llm_fn,
                ensemble_weights=ensemble_weights,
            )
            messages = _build_messages(query, context_chunks)
            sources  = _format_sources(context_chunks)

            yield sse("start", {
                "chat_id": chat_id, "query": query,
                "provider": provider, "model": model, "strategy": strategy,
            })

            async for token in llm.stream(messages, provider, model, temperature):
                yield sse("chunk", {"content": token})

            yield sse("sources", {"source_chunks": sources, "sources_count": len(sources)})
            yield sse("done",    {"chat_id": chat_id})

        except Exception as e:
            logger.error("stream error chat_id=%s: %s", chat_id, e)
            yield sse("error", {"message": str(e)})
