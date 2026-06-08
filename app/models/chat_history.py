import enum
import uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, Float, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.db import Base, UUIDPKMixin, TimestampMixin


class ChatMode(str, enum.Enum):
    document = "document"
    candidate = "candidate"
    hybrid = "hybrid"
    job_match = "job_match"


class ChatHistory(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "chat_history"

    chat_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    query: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)          # full streamed response saved after completion
    mode: Mapped[ChatMode | None] = mapped_column(SAEnum(ChatMode), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)    # "openai"
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)      # "gpt-4o-mini"
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_chunks: Mapped[dict | None] = mapped_column(JSONB, nullable=True)   # retrieved context metadata
    response_blocks: Mapped[dict | None] = mapped_column(JSONB, nullable=True) # structured JSON blocks

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )