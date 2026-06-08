import uuid
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.db import get_db
from app.core.security import get_current_user_id
from app.models.user import User
from app.schemas import CandidateCreate, CandidateOut, CandidateUpdate
from app.services.candidate_service import CandidateService

candidate_route = APIRouter()


@candidate_route.post("/upload", response_model=CandidateOut, status_code=status.HTTP_201_CREATED)
async def upload_candidate(
    name: str = Form(...),
    email: str = Form(...),
    phone: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    experience: Optional[float] = Form(None),
    skills: Optional[str] = Form(None),          # comma-separated: "Python,FastAPI,Redis"
    current_role: Optional[str] = Form(None),
    expected_salary: Optional[str] = Form(None),
    notice_period: Optional[int] = Form(None),
    resume: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_id),
):
    skills_list = [s.strip() for s in skills.split(",")] if skills else []

    payload = CandidateCreate(
        candidate_id=f"cand_{uuid.uuid4().hex[:6]}",
        name=name,
        email=email,
        phone=phone,
        location=location,
        experience=experience,
        skills=skills_list,
        current_role=current_role,
        expected_salary=expected_salary,
        notice_period=notice_period,
        uploaded_by=current_user.id,
    )
    return await CandidateService.upload(db=db, payload=payload, resume=resume)


@candidate_route.get("/", response_model=List[CandidateOut])
async def list_candidates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_id),
):
    return await CandidateService.list_all(db=db, user_id=current_user.id)


@candidate_route.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_id),
):
    candidate = await CandidateService.get_by_candidate_id(db=db, candidate_id=candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


@candidate_route.get("/{candidate_id}/status", response_model=CandidateOut)
async def get_candidate_status(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_id),
):
    candidate = await CandidateService.get_by_candidate_id(db=db, candidate_id=candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


@candidate_route.patch("/{candidate_id}", response_model=CandidateOut)
async def update_candidate(
    candidate_id: str,
    payload: CandidateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_id),
):
    candidate = await CandidateService.update(db=db, candidate_id=candidate_id, payload=payload)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


@candidate_route.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_id),
):
    deleted = await CandidateService.delete(db=db, candidate_id=candidate_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Candidate not found")