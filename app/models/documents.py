import enum
import uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from app.core.db import Base, UUIDPKMixin, TimestampMixin


class DocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    done = "done"
    failed = "failed"


class Document(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    document_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str | None] = mapped_column(String(10), nullable=True)   # "pdf" / "txt"
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)  # local upload path
    pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(DocumentStatus), default=DocumentStatus.uploaded
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[str | None] = mapped_column(nullable=True)

    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )