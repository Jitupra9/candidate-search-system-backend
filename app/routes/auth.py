from fastapi import APIRouter, Depends
from app.schemas.response import ApiResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.security import get_current_user_id
from app.services.auth_service import register_user, login_user, get_me
from app.schemas.auth import LoginRequest,RegisterRequest
auth_router = APIRouter()



# ── Routes ────────────────────────────────────────────────────
@auth_router.post("/register", status_code=201,response_model=ApiResponse)

async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    return await register_user(db, body.name, body.email, body.password)


@auth_router.post("/login",response_model=ApiResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    return await login_user(db, body.email, body.password)


@auth_router.get("/me",response_model=ApiResponse)
async def me(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await get_me(db, user_id)