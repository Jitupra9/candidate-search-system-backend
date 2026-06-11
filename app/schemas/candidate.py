import uuid
import enum
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from app.models.candidates import CandidateStatus




# ─── Insert (request) ────────────────────────────────────────────────────────

class CandidateCreate(BaseModel):
    resume_file_url: Optional[str] = None
    uploaded_by: Optional[uuid.UUID] = None


# ─── Update ──────────────────────────────────────────────────────────────────

class CandidateUpdate(BaseModel):
    status: Optional[CandidateStatus] = None
    error_message: Optional[str] = None
    processed_at: Optional[datetime] = None
    summary: Optional[str] = None
    skills: Optional[List[str]] = None
    resume_file_url: Optional[str] = None


# ─── Output (response) ───────────────────────────────────────────────────────

class CandidateOut(BaseModel):
    id: uuid.UUID
    candidate_id: str
    resume_file_url: Optional[str] = None
    status: CandidateStatus
    error_message: Optional[str] = None
    uploaded_by: Optional[uuid.UUID] = None
    location:Optional[str] = None
    processed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}