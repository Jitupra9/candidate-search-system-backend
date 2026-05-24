from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.schemas.response import ApiResponse


def register_exception_handlers(app: FastAPI) -> None:

    # ── HTTPException (401, 403, 404, 400 etc) ───────────────
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=ApiResponse.error(message=exc.detail).model_dump(),
        )


    # ── Validation Error (wrong request body/params) ──────────
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        # extract first error message cleanly
        errors = exc.errors()
        first_error = errors[0]
        field = " → ".join(str(loc) for loc in first_error["loc"] if loc != "body")
        message = f"{field}: {first_error['msg']}" if field else first_error["msg"]

        return JSONResponse(
            status_code=422,
            content=ApiResponse.error(message=message).model_dump(),
        )


    # ── Unhandled Exception (500) ─────────────────────────────
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content=ApiResponse.error(message="Internal server error").model_dump(),
        )