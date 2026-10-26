"""FastAPI application factory. Run: ``uvicorn codeforge_api.main:app``."""

import logging
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from codeforge_core import logging as cflog
from codeforge_core import queue as cfqueue
from codeforge_core.config import get_settings
from codeforge_core.redis_client import get_redis

from .errors import install_error_handlers
from .middleware import RequestContextMiddleware
from .routers import auth, problems, submissions, system, users

log = logging.getLogger("codeforge_api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    cflog.configure_logging("api", s.log_level)
    if s.environment != "development" and s.jwt_secret.startswith("dev-only"):
        raise RuntimeError("JWT_SECRET must be set outside development")
    try:
        cfqueue.ensure_groups(get_redis())
    except redis.RedisError as exc:
        log.warning("redis not reachable at startup; continuing degraded", extra={"error": str(exc)})
    system.register_collectors()
    log.info("api started")
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="CodeForge API",
        version="1.0.0",
        description="Distributed online judge: problems, asynchronous judged submissions, realtime status (SSE).",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Last-Event-ID", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )
    install_error_handlers(app)
    for r in (system.router, auth.router, problems.router, submissions.router, users.router):
        app.include_router(r)
    return app


app = create_app()
