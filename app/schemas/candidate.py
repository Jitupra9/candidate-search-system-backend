import uuid
import enum
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from app.models.candidates import CandidateStatus

class CandidateExtraction(BaseModel):

    name: str | None = Field(
        default=None, description="Full name of the candidate as it appears on the resume"
    )
    email: str | None = Field(
        default=None, description="Primary email address of the candidate"
    )
    phone: str | None = Field(
        default=None, description="Primary contact phone number, including country code if present"
    )
    location: str | None = Field(
        default=None, description="Candidate's current city and/or country of residence"
    )
    current_role: str | None = Field(
        default=None, description="Candidate's most recent or current job title"
    )
    experience: float | None = Field(
        default=None, description="Total years of professional experience, expressed as a number (e.g. 3.5)"
    )
    skills: list[str] = Field(
        default_factory=list,
        description="List of technical and professional skills mentioned in the resume (e.g. ['Python', 'FastAPI', 'Docker'])",
    )
    expected_salary: str | None = Field(
        default=None, description="Candidate's expected salary or compensation, as stated in the resume, including currency/unit if mentioned"
    )
    notice_period: int | None = Field(
        default=None, description="Notice period required before joining, expressed in days (e.g. 30)"
    )
    summary: str | None = Field(
        default=None, description="A brief 1-3 sentence professional summary of the candidate's background"
    )

    @field_validator("skills", mode="before")
    @classmethod
    def _coerce_skills(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v
    @field_validator("notice_period", mode="before")
    @classmethod
    def _coerce_notice_period(cls, v):
        if v is None or isinstance(v, int):
            return v
        if isinstance(v, str):
            digits = "".join(c for c in v if c.isdigit())
            if not digits:
                return None
            num = int(digits)
            if "month" in v.lower():
                return num * 30
            return num
        return v

    @field_validator("experience", mode="before")
    @classmethod
    def _coerce_experience(cls, v):
        if v is None or isinstance(v, (int, float)):
            return v
        if isinstance(v, str):
            cleaned = "".join(c for c in v if c.isdigit() or c == ".")
            return float(cleaned) if cleaned else None
        return v
# ─── Insert (request) ────────────────────────────────────────────────────────

class CandidateCreate(BaseModel):
    resume_file_url: Optional[str] = None
    uploaded_by: Optional[uuid.UUID] = None
    provider:Optional[str] =None
    model:Optional[str] = None


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