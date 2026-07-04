import logging
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from app.core.config import settings

logger = logging.getLogger(__name__)


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_logger(request: Request, call_next):
        start    = time.perf_counter()
        response = await call_next(request)
        ms       = (time.perf_counter() - start) * 1000
        logger.info("%s %s → %s  %.1fms",
                    request.method, request.url.path, response.status_code, ms)
        return response
