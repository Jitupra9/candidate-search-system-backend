import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, Any, Literal
from app.models.chat_history import ChatMode
from app.core.config import settings


class ChatHistoryBase(BaseModel):
    query: str
    mode: Optional[ChatMode] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0)


class ChatHistoryCreate(ChatHistoryBase):
    chat_id: str
    user_id: Optional[uuid.UUID] = None
    response: Optional[str] = None
    source_chunks: Optional[Any] = None


class ChatHistoryUpdate(BaseModel):
    response: Optional[str] = None
    source_chunks: Optional[Any] = None


class ChatHistoryOut(ChatHistoryBase):
    id: uuid.UUID
    chat_id: str
    user_id: Optional[uuid.UUID] = None
    response: Optional[str] = None
    source_chunks: Optional[Any] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    query: str
    provider: str = Field(default_factory=lambda: settings.DEFAULT_PROVIDER, description="openai | anthropic | groq | ollama | gemini")
    model:    str = Field(default_factory=lambda: settings.DEFAULT_MODEL,    description="Model name for the selected provider")
    temperature:      float = Field(default=0.7, ge=0.0, le=2.0)
    strategy: Literal[
        "pipeline",
        "similarity", "mmr", "multi_query",
        "contextual", "self_query", "hybrid_bm25", "ensemble"
    ] = Field(default="pipeline", description="Retrieval strategy — pipeline is recommended")
    k:                int            = Field(default=5,    ge=1, le=20)
    filters:          Optional[dict] = Field(default=None, description="ChromaDB metadata filters")
    ensemble_weights: Optional[dict] = Field(default=None, description="Weights for ensemble strategy")
    mode:             Optional[ChatMode] = None
