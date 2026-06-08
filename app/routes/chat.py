import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.db import get_db
from app.core.security import  get_current_user
from app.models.user import User
from app.schemas import ChatRequest, ChatResponse, ChatHistoryOut
from app.services.chat_servie import ChatService

ask_api_router = APIRouter()


@ask_api_router.post("/query")
async def chat_query(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Unified chat endpoint — streams SSE response.
    Supports: document QA, candidate search, hybrid, job match.
    """
    chat_id = f"chat_{uuid.uuid4().hex[:8]}"

    async def event_stream():
        try:
            async for chunk in ChatService.stream(
                db=db,
                chat_id=chat_id,
                user_id=current_user.id,
                payload=payload,
            ):
                yield f"data: {chunk}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n"
        finally:
            yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",    
            "Connection": "keep-alive",
        },
    )


@ask_api_router.get("/history", response_model=List[ChatHistoryOut])
async def get_chat_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await ChatService.get_history(db=db, user_id=current_user.id)


@ask_api_router.get("/history/{chat_id}", response_model=ChatHistoryOut)
async def get_chat_by_id(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = await ChatService.get_by_chat_id(db=db, chat_id=chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@ask_api_router.delete("/history/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deleted = await ChatService.delete(db=db, chat_id=chat_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Chat not found")