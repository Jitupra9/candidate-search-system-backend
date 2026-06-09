import uuid
import enum
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from app.models.candidates import CandidateStatus


# ─── Base ────────────────────────────────────────────────────────────────────

class CandidateBase(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    location: Optional[str] = None
    experience: Optional[float] = None
    skills: Optional[List[str]] = Field(default_factory=list)
    current_role: Optional[str] = None
    expected_salary: Optional[str] = None
    notice_period: Optional[int] = None
    summary: Optional[str] = None
    status:Optional[str] = None


# ─── Insert (request) ────────────────────────────────────────────────────────

class CandidateCreate(CandidateBase):
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

class CandidateOut(CandidateBase):
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