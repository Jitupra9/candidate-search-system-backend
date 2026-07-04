import asyncio
import logging
import uuid
from app.core.db import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from app.models.candidates import Candidate
from app.schemas.response import ApiResponse
from app.schemas.candidate import CandidateCreate, CandidateOut, CandidateUpdate
from app.workers.candidate_tasks import process_candidate_resume
from app.core.chroma_client import chroma
logger = logging.getLogger(__name__)


class CandidateService:

    @staticmethod
    async def upload(db: AsyncSession, payload: CandidateCreate, uploaded_by: uuid.UUID):
        if not payload.resume_file_url:
            logger.warning("upload rejected — missing resume_file_url user_id=%s", uploaded_by)
            return ApiResponse.error(message="resume_file_url is required")

        candidate = Candidate(
            resume_file_url=payload.resume_file_url,
            uploaded_by=uploaded_by,
        )
        db.add(candidate)
        await db.flush()   
        await db.commit()

        task = process_candidate_resume.delay(
            resume_url=payload.resume_file_url,
            candidate_id=str(candidate.id),
        )

        return ApiResponse.success(
            data={"candidate_id": str(candidate.id), "task_id": task.id},
            message="Candidate uploaded successfully",
        )

    @staticmethod
    async def list_all(db: AsyncSession):
        logger.debug("list_all candidates")
        result = await db.execute(select(Candidate).order_by(Candidate.created_at.desc()))
        candidates = result.scalars().all()
        logger.debug("list_all — returned %d candidates", len(candidates))
        return ApiResponse.success(
            data=[CandidateOut.model_validate(c) for c in candidates],
            message="Candidates retrieved successfully",
        )
    @staticmethod
    async def get_by_id(db: AsyncSession, candidate_id: str):
        logger.debug("get_by_id — candidate_id=%s", candidate_id)
        candidate = await db.get(Candidate, uuid.UUID(candidate_id))
        if not candidate:
            logger.warning("get_by_id — not found: %s", candidate_id)
            raise HTTPException(status_code=404, detail="Candidate not found")
        return ApiResponse.success(data=CandidateOut.model_validate(candidate))

    @staticmethod
    async def delete(db: AsyncSession, candidate_id: str):
        logger.debug("delete — candidate_id=%s", candidate_id)
        candidate = await db.get(Candidate, uuid.UUID(candidate_id))
        if not candidate:
            logger.warning("delete — not found: %s", candidate_id)
            raise HTTPException(status_code=404, detail="Candidate not found")
        await db.delete(candidate)
        await db.commit()
        chroma.collection.delete(where={"candidate_id": candidate_id})
        logger.info("deleted — candidate_id=%s", candidate_id)
        return ApiResponse.success(message="Candidate removed successfully")

