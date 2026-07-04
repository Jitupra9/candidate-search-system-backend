from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas import CandidateCreate, CandidateOut, CandidateUpdate
from app.services.candidate_service import CandidateService

candidate_route = APIRouter()


@candidate_route.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_candidate(
    payload: CandidateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await CandidateService.upload(db=db, payload=payload, uploaded_by=current_user.id)


@candidate_route.get("/")
async def list_candidates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await CandidateService.list_all(db=db)


@candidate_route.get("/{candidate_id}")
async def get_candidate(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await CandidateService.get_by_id(db=db, candidate_id=candidate_id)

@candidate_route.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await CandidateService.delete(db=db, candidate_id=candidate_id)
