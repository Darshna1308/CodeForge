import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from codeforge_core import logging as cflog

from .metrics import HTTP_LATENCY, HTTP_REQUESTS

log = logging.getLogger("codeforge_api.access")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, binds it to the log context, records access logs and metrics."""

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID.match(incoming) else uuid.uuid4().hex[:16]
        token = cflog.bind(request_id=request_id)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            elapsed = time.perf_counter() - started
            route = request.scope.get("route")
            route_path = getattr(route, "path", "unmatched")  # template, not raw path: bounded cardinality
            HTTP_REQUESTS.labels(request.method, route_path, str(status)).inc()
            HTTP_LATENCY.labels(request.method, route_path).observe(elapsed)
            if route_path not in ("/health", "/metrics"):
                log.info(
                    "request",
                    extra={"method": request.method, "route": route_path, "status": status,
                           "duration_ms": round(elapsed * 1000, 2)},
                )
            cflog.reset(token)
