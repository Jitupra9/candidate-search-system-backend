from fastapi import APIRouter
from app.routes.auth import auth_router as auth_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
# api_router.include_router(user_router, prefix="/user", tags=["User"] , dependencies=[Depends(get_current_user_id)]  # ← entire router protected)