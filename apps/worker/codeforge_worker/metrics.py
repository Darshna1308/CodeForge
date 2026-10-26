from prometheus_client import Counter, Gauge, Histogram

JOBS = Counter("codeforge_worker_jobs_total", "Jobs handled by outcome", ["outcome"])
VERDICTS = Counter("codeforge_worker_verdicts_total", "Final verdicts", ["verdict", "language", "mode"])
JOB_SECONDS = Histogram(
    "codeforge_worker_job_seconds", "Claim-to-finish job duration",
    buckets=(0.25, 0.5, 1, 2, 4, 8, 16, 32, 64),
)
QUEUE_WAIT_SECONDS = Histogram(
    "codeforge_worker_queue_wait_seconds", "Enqueue-to-claim latency",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
SANDBOX_START_SECONDS = Histogram(
    "codeforge_worker_sandbox_start_seconds", "Container start to runner handshake",
    buckets=(0.1, 0.25, 0.5, 1, 2, 4, 8),
)
COMPILE_SECONDS = Histogram("codeforge_worker_compile_seconds", "Compilation wall time", buckets=(0.05, 0.25, 0.5, 1, 2, 4, 8, 16))
DUPLICATES = Counter("codeforge_worker_duplicate_deliveries_total", "Deliveries skipped because the submission was already claimed or finished")
REDELIVERIES = Counter("codeforge_worker_redeliveries_total", "Messages recovered via XAUTOCLAIM")
DEAD_LETTERED = Counter("codeforge_worker_dead_lettered_total", "Messages moved to the dead-letter stream")
SANDBOX_FAILURES = Counter("codeforge_worker_sandbox_failures_total", "Infrastructure failures inside a job")
BUSY = Gauge("codeforge_worker_busy_slots", "Consumer threads currently executing a job")
SWEEPER_ACTIONS = Counter("codeforge_worker_sweeper_actions_total", "Sweeper recoveries", ["action"])
