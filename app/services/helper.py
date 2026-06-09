from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from app.schemas.response import ApiResponse

async def unique_check(db: AsyncSession, model, key: str, value):
    column = getattr(model, key)

    result = await db.execute(
        select(model).where(column == value)
    )

    existing = result.scalar_one_or_none()

    if existing:
        return True
    return False