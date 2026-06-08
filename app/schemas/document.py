import uuid
import enum
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional
from app.models.documents import DocumentStatus


# ─── Base ────────────────────────────────────────────────────────────────────

class DocumentBase(BaseModel):
    file_name: str
    file_type: Optional[str] = None
    pages: Optional[int] = None


# ─── Insert (request) ────────────────────────────────────────────────────────

class DocumentCreate(DocumentBase):
    document_id: str
    file_path: Optional[str] = None
    uploaded_by: Optional[uuid.UUID] = None


# ─── Update ──────────────────────────────────────────────────────────────────

class DocumentUpdate(BaseModel):
    status: Optional[DocumentStatus] = None
    error_message: Optional[str] = None
    processed_at: Optional[datetime] = None
    pages: Optional[int] = None


# ─── Output (response) ───────────────────────────────────────────────────────

class DocumentOut(DocumentBase):
    id: uuid.UUID
    document_id: str
    file_path: Optional[str] = None
    status: DocumentStatus
    error_message: Optional[str] = None
    uploaded_by: Optional[uuid.UUID] = None
    processed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}