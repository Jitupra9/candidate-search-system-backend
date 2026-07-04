import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.schemas.response import ApiResponse
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:

    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        logger.warning("HTTP %s — %s %s", exc.status_code, request.method, request.url.path)
        return JSONResponse(
            status_code=exc.status_code,
            content=ApiResponse.error(message=exc.detail).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        first  = errors[0]
        field  = " → ".join(str(loc) for loc in first["loc"] if loc != "body")
        message = f"{field}: {first['msg']}" if field else first["msg"]
        logger.warning("validation error — %s %s — %s", request.method, request.url.path, message)
        return JSONResponse(
            status_code=422,
            content=ApiResponse.error(message=message).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # extract the root cause — skip SQLAlchemy wrapper chains
        cause = exc.__cause__ or exc.__context__ or exc
        logger.error(
            "500 %s %s — %s: %s",
            request.method, request.url.path,
            type(cause).__name__, cause,
        )
        return JSONResponse(
            status_code=500,
            content=ApiResponse.error(message="Internal server error").model_dump(),
        )
