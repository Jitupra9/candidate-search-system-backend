from fastapi import APIRouter,  Form, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.db import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas import CandidateCreate, CandidateOut, CandidateUpdate
from app.services.candidate_service import CandidateService

candidate_route = APIRouter()


@candidate_route.post("/upload", response_model=CandidateOut, status_code=status.HTTP_201_CREATED)
async def upload_candidate(
    payload: CandidateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await CandidateService.upload(db=db, payload=payload)


@candidate_route.get("/", response_model=List[CandidateOut])
async def list_candidates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await CandidateService.list_all(db=db)


@candidate_route.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await CandidateService.get_by_candidate_id(db=db, candidate_id=candidate_id)
    


@candidate_route.patch("/{candidate_id}", response_model=CandidateOut)
async def update_candidate(
    candidate_id: str,
    payload: CandidateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
   return await CandidateService.update(db=db, candidate_id=candidate_id, payload=payload)
    


@candidate_route.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
   return await CandidateService.delete(db=db, candidate_id=candidate_id)
