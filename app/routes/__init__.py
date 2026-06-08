from fastapi import APIRouter
from app.routes.auth import auth_router as auth_router
from app.routes.chat import ask_api_router
from app.routes.candidate import candidate_route
from app.routes.documents import document_route
api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_router.include_router(ask_api_router,prefix="/chat", tags=["Chat"])
api_router.include_router(candidate_route,prefix="/candidates", tags=["Candidates"])
api_router.include_router(document_route,prefix="/documents", tags=["Documents"])