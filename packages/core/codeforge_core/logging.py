"""Structured JSON logging with request/submission/worker context.

Context is carried in contextvars so it flows through function calls without
being threaded through every signature, and is safe across threads and
asyncio tasks. Source code and test data are never logged.
"""

import json
import logging
import sys
import time
from contextvars import ContextVar
from typing import Any

_context: ContextVar[dict[str, Any]] = ContextVar("cf_log_context", default={})

_RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime"}


def bind(**fields: Any):
    """Bind fields to the current context. Returns a token for :func:`reset`."""
    merged = {**_context.get(), **{k: v for k, v in fields.items() if v is not None}}
    return _context.set(merged)


def reset(token) -> None:
    _context.reset(token)


def current_context() -> dict[str, Any]:
    return dict(_context.get())


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update(_context.get())
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(service: str, level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
