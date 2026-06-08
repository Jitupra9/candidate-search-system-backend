import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, Any
from app.models.chat_history import ChatMode


# ─── Base ────────────────────────────────────────────────────────────────────

class ChatHistoryBase(BaseModel):
    query: str
    mode: Optional[ChatMode] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0)


# ─── Insert (request) ────────────────────────────────────────────────────────

class ChatHistoryCreate(ChatHistoryBase):
    chat_id: str
    user_id: Optional[uuid.UUID] = None
    response: Optional[str] = None
    source_chunks: Optional[Any] = None
    response_blocks: Optional[Any] = None


# ─── Update (save response after stream completes) ───────────────────────────

class ChatHistoryUpdate(BaseModel):
    response: Optional[str] = None
    source_chunks: Optional[Any] = None
    response_blocks: Optional[Any] = None


# ─── Output (response) ───────────────────────────────────────────────────────

class ChatHistoryOut(ChatHistoryBase):
    id: uuid.UUID
    chat_id: str
    user_id: Optional[uuid.UUID] = None
    response: Optional[str] = None
    source_chunks: Optional[Any] = None
    response_blocks: Optional[Any] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Chat Request (incoming API call) ────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str
    mode: Optional[ChatMode] = None          # if None, system auto-detects
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


# ─── Chat Response (non-streaming) ───────────────────────────────────────────

class ChatResponse(BaseModel):
    chat_id: str
    query: str
    mode: ChatMode
    response: str
    source_chunks: Optional[Any] = None
    response_blocks: Optional[Any] = None
    provider: str
    model: str