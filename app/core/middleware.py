from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware



def register_middleware(app: FastAPI) -> None:
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL],   # ← reads from .env
        allow_credentials=True,                  # ← allows cookies/auth headers
        allow_methods=["*"],                     # ← GET, POST, PUT, DELETE etc
        allow_headers=["*"],                     # ← Authorization, Content-Type etc
    )