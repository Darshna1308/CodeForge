"""Every Redis key CodeForge uses, in one place (documented in docs/QUEUE_AND_CONCURRENCY.md)."""

# Job queues (Redis Streams + one consumer group each)
STREAM_RUN = "cf:q:run"  # interactive "Run Code" jobs, higher priority
STREAM_SUBMIT = "cf:q:submit"  # judged submissions
STREAM_DEAD = "cf:q:dead"  # dead-letter: exceeded delivery attempts
CONSUMER_GROUP = "judges"

# Worker liveness registry: one hash per worker, expires unless heartbeated
WORKER_PREFIX = "cf:worker:"
SWEEPER_LOCK = "cf:lock:sweeper"

# Global counters maintained by workers (dashboard)
COUNTER_JOBS_COMPLETED = "cf:stats:jobs_completed"
COUNTER_JOBS_FAILED = "cf:stats:jobs_failed"
COUNTER_DUPLICATES = "cf:stats:duplicate_deliveries"
COUNTER_REDELIVERED = "cf:stats:redelivered"


def submission_events(submission_id: int) -> str:
    return f"cf:sub:{submission_id}:events"


def worker_key(worker_id: str) -> str:
    return f"{WORKER_PREFIX}{worker_id}"


# Cache-aside (generation-based invalidation)
CACHE_GENERATION = "cf:cache:problems:gen"


def cache_problem_list(gen: int, fingerprint: str) -> str:
    return f"cf:cache:problems:v{gen}:list:{fingerprint}"


def cache_problem(gen: int, slug: str) -> str:
    return f"cf:cache:problems:v{gen}:detail:{slug}"


def cache_stats(name: str) -> str:
    return f"cf:cache:stats:{name}"


def rate_limit(bucket: str, subject: str) -> str:
    return f"cf:rl:{bucket}:{subject}"


def revoked_token(jti: str) -> str:
    return f"cf:auth:revoked:{jti}"
