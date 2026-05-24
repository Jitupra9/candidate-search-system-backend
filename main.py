from fastapi import FastAPI
from app.core.config import settings
from app.routes import api_router         
from app.core.middleware import register_middleware
from app.core.exceptions import register_exception_handlers

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
)

register_middleware(app=app)
register_exception_handlers(app)
app.include_router(api_router, prefix="/api/v1")
