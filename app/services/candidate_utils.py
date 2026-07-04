from sqlalchemy.ext.asyncio import AsyncSession
import logging
import asyncio
from app.core.db import AsyncSessionLocal
from app.models.candidates import Candidate
import uuid
from app.schemas.candidate import CandidateExtraction
logger = logging.getLogger(__name__)

def update_candidate_from_task(candidate_id: str, data: CandidateExtraction | None, status: str) -> None:
    """Sync wrapper — call this from the Celery task (which is sync)."""
    asyncio.run(_update_candidate_from_task_async(candidate_id, data, status))

async def _update_candidate_from_task_async(candidate_id, data, status):
    fields = data.model_dump(exclude_none=True) if data else {}
    fields["status"] = status

    async with AsyncSessionLocal() as db:
        candidate = await _apply_candidate_update(db, candidate_id, fields)
        if not candidate:
            logger.warning("Celery update — candidate not found: %s", candidate_id)
async def _apply_candidate_update(
    db: AsyncSession,
    candidate_id: str,
    fields: dict,
) -> Candidate | None:
    """
    Core update logic, shared by the API route and the Celery task.
    Takes whatever session it's given — caller owns the session lifecycle.
    """
    candidate = await db.get(Candidate, uuid.UUID(candidate_id))
    if not candidate:
        logger.warning("update — not found: %s", candidate_id)
        return None

    for field, value in fields.items():
        setattr(candidate, field, value)

    await db.commit()
    logger.info("updated — candidate_id=%s fields=%s", candidate_id, list(fields.keys()))
    return candidate


