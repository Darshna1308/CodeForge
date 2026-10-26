"""Worker process entrypoint: ``python -m codeforge_worker.main``."""

import logging
import os
import signal
import socket
import threading
import time

import redis
from prometheus_client import start_http_server

from codeforge_core import logging as cflog
from codeforge_core import queue as cfqueue
from codeforge_core.config import get_settings
from codeforge_core.db import get_sessionmaker
from codeforge_core.redis_client import get_redis

from .consumer import Consumer
from .registry import Heartbeat
from .sandbox import reap_stale_containers
from .sweeper import Sweeper

log = logging.getLogger("codeforge_worker")


def default_worker_id() -> str:
    return f"worker-{socket.gethostname()[:8]}-{os.getpid()}"


def main() -> None:
    settings = get_settings()
    worker_id = settings.worker_id or default_worker_id()
    cflog.configure_logging("worker", settings.log_level)
    cflog.bind(worker_id=worker_id)

    r = get_redis()
    sessions = get_sessionmaker()

    delay = 1.0
    while True:
        try:
            cfqueue.ensure_groups(r)
            break
        except redis.RedisError as exc:
            log.warning("waiting for redis", extra={"error": str(exc)})
            time.sleep(delay)
            delay = min(delay * 2, 10)

    reap_stale_containers(settings, older_than_s=0 if settings.environment == "development" else 300)
    start_http_server(settings.worker_metrics_port)

    stop = threading.Event()
    stats = {"busy": 0, "handled": 0}
    consumers = [Consumer(i, settings, r, sessions, worker_id, stop, stats) for i in range(settings.worker_concurrency)]
    threads: list[threading.Thread] = [
        *consumers,
        Heartbeat(r, worker_id, settings.worker_concurrency, stats, stop),
        Sweeper(settings, r, sessions, worker_id, stop),
    ]
    for t in threads:
        t.start()
    log.info("worker started", extra={"concurrency": settings.worker_concurrency, "sandbox_image": settings.sandbox_image})

    def shutdown(signum, _frame):
        log.info("shutdown requested; draining in-flight jobs", extra={"signal": signum})
        stop.set()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    while not stop.is_set():
        stop.wait(1)
    deadline = time.monotonic() + 60
    for c in consumers:
        c.join(timeout=max(0, deadline - time.monotonic()))
    log.info("worker stopped", extra={"handled": stats["handled"]})


if __name__ == "__main__":
    main()
