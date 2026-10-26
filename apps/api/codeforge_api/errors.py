"""Structured error responses: {"error": {"code", "message", "details", "request_id"}}."""

import logging
from typing import Any

import redis
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from codeforge_core import logging as cflog

log = logging.getLogger(__name__)


class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: Any = None, headers: dict | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers


def error_body(code: str, message: str, details: Any = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details, "request_id": cflog.current_context().get("request_id")}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error(_: Request, exc: APIError):
        return JSONResponse(error_body(exc.code, exc.message, exc.details), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [
            {"loc": [str(p) for p in e.get("loc", [])], "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()
        ]
        return JSONResponse(error_body("validation_error", "Request validation failed", details), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed", 401: "unauthorized", 403: "forbidden"}.get(exc.status_code, "http_error")
        return JSONResponse(error_body(code, str(exc.detail)), status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(OperationalError)
    async def _db_down(_: Request, exc: OperationalError):
        log.error("database unavailable", extra={"error": str(exc.orig)[:200] if exc.orig else str(exc)[:200]})
        return JSONResponse(error_body("database_unavailable", "The database is temporarily unavailable"), status_code=503, headers={"Retry-After": "5"})

    @app.exception_handler(redis.ConnectionError)
    async def _redis_down(_: Request, exc: redis.ConnectionError):
        log.error("redis unavailable", extra={"error": str(exc)[:200]})
        return JSONResponse(error_body("queue_unavailable", "The job queue is temporarily unavailable"), status_code=503, headers={"Retry-After": "5"})

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse(error_body("internal_error", "Internal server error"), status_code=500)
