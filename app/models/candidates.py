import enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Float, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from app.core.db import Base, UUIDPKMixin, TimestampMixin
import uuid


class CandidateStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    done = "done"
    failed = "failed"


class Candidate(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "candidates"

    candidate_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    experience: Mapped[float | None] = mapped_column(Float, nullable=True)
    skills: Mapped[list | None] = mapped_column(ARRAY(String), default=list)
    current_role: Mapped[str | None] = mapped_column(String(150), nullable=True)
    expected_salary: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notice_period: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resume_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[CandidateStatus] = mapped_column(
        SAEnum(CandidateStatus), default=CandidateStatus.uploaded
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[str | None] = mapped_column(nullable=True)  # handled by TimestampMixin pattern

    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )