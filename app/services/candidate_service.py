import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from app.models.candidates import Candidate, CandidateStatus
from app.schemas.response import ApiResponse
from app.schemas.candidate import CandidateCreate, CandidateOut, CandidateUpdate
from app.workers.candidate_tasks import process_candidate_resume


class CandidateService:

    @staticmethod
    async def upload(db: AsyncSession, payload: CandidateCreate, uploaded_by: uuid.UUID):
        if not payload.resume_file_url:
            return ApiResponse.error(message="resume_file_url is required")

        # 1. Create candidate row in PostgreSQL with status=processing
        candidate = Candidate(
            resume_file_url=payload.resume_file_url,
            uploaded_by=uploaded_by,
            status=CandidateStatus.processing,
            # name/email/skills etc. will be filled by Celery task after LLM extraction
        )
        db.add(candidate)
        await db.flush()   # get candidate.id without committing

        # 2. Dispatch Celery task with the real candidate.id
        task = process_candidate_resume.delay(
            resume_url=payload.resume_file_url,
            candidate_id=str(candidate.id),
        )

        return ApiResponse.success(
            data={"task_id": task.id, "candidate_id": str(candidate.id), "status": "processing"},
            message="Resume processing started",
        )

    @staticmethod
    async def list_all(db: AsyncSession):
        result = await db.execute(select(Candidate).order_by(Candidate.created_at.desc()))
        candidates = result.scalars().all()
        return ApiResponse.success(
            data=[CandidateOut.model_validate(c) for c in candidates],
            message="Candidates retrieved successfully",
        )

    @staticmethod
    async def get_by_id(db: AsyncSession, candidate_id: str):
        candidate = await db.get(Candidate, uuid.UUID(candidate_id))
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
        return ApiResponse.success(data=CandidateOut.model_validate(candidate))

    @staticmethod
    async def delete(db: AsyncSession, candidate_id: str):
        candidate = await db.get(Candidate, uuid.UUID(candidate_id))
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
        await db.delete(candidate)
        return ApiResponse.success(message="Candidate removed successfully")

    @staticmethod
    async def update(db: AsyncSession, candidate_id: str, payload: CandidateUpdate):
        candidate = await db.get(Candidate, uuid.UUID(candidate_id))
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(candidate, field, value)
        await db.flush()
        return ApiResponse.success(
            data=CandidateOut.model_validate(candidate),
            message="Candidate updated successfully",
        )
