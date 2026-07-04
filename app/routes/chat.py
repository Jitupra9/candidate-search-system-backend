from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.chat_history import ChatRequest
from app.services.chat_servie import ChatService
from app.llm import list_models as get_llm_models

ask_api_router = APIRouter()


@ask_api_router.post("/query")
async def chat_query(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Non-streaming RAG query — returns complete response at once.
    Use this for testing. Use /query/stream for frontend production use.
    """
    return await ChatService.ask(
        query=payload.query,
        provider=payload.provider,
        model=payload.model,
        temperature=payload.temperature,
        strategy=payload.strategy,
        k=payload.k,
        filters=payload.filters,
        ensemble_weights=payload.ensemble_weights,
    )


@ask_api_router.post("/query/stream")
async def chat_query_stream(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Streaming RAG query — Server-Sent Events (SSE).

    SSE event sequence:
      data: {"type": "start",   "chat_id": "...", "query": "...", "provider": "...", "model": "...", "strategy": "..."}
      data: {"type": "chunk",   "content": "word"}       ← one per LLM token
      data: {"type": "sources", "source_chunks": [...], "sources_count": 5}
      data: {"type": "done",    "chat_id": "..."}
      data: {"type": "error",   "message": "..."}        ← only on failure
    """
    return StreamingResponse(
        ChatService.ask_stream(
            query=payload.query,
            provider=payload.provider,
            model=payload.model,
            temperature=payload.temperature,
            strategy=payload.strategy,
            k=payload.k,
            filters=payload.filters,
            ensemble_weights=payload.ensemble_weights,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",      # disables nginx buffering
            "Connection":       "keep-alive",
        },
    )


@ask_api_router.get("/models")
async def list_models(current_user: User = Depends(get_current_user)):
    """List all available providers and their supported models."""
    return {"ok": True, "data": get_llm_models()}
