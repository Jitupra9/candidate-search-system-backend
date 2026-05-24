from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from app.schemas.response import ApiResponse
from app.models.user import User
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
)


async def register_user(db: AsyncSession, name: str, email: str, password: str) -> dict:
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = User(
        name=name,
        email=email,
        password=hash_password(password),
    )
    db.add(user)
    await db.flush()
    return ApiResponse.success(message="Registered successfully")


async def login_user(db: AsyncSession, email: str, password: str) -> dict:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return ApiResponse.success(
        message="Login successful",
        data={
            "access_token": create_access_token({"sub": str(user.id)}),
            "refresh_token": create_refresh_token({"sub": str(user.id)}),
            "token_type": "bearer",
        }
    )


async def get_me(db: AsyncSession, user_id: str) -> dict:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return ApiResponse.success(
        message="User fetched successfully",
        data={
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
        }
    )