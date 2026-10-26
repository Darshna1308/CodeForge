from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter("codeforge_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram(
    "codeforge_http_request_seconds", "HTTP request latency", ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
CACHE = Counter("codeforge_cache_requests_total", "Cache-aside lookups", ["cache", "result"])
RATE_LIMITED = Counter("codeforge_rate_limited_total", "Requests rejected by the rate limiter", ["bucket"])
SUBMISSIONS_CREATED = Counter("codeforge_submissions_created_total", "Submissions accepted by the API", ["mode", "language"])
ENQUEUE_FAILURES = Counter("codeforge_enqueue_failures_total", "XADD failures after commit (recovered by the sweeper)")
SSE_CONNECTIONS = Counter("codeforge_sse_connections_total", "SSE connections opened")
