"""Worker liveness registry: a Redis hash per worker with a short TTL.

A worker is "active" exactly as long as it keeps refreshing its key, so the
dashboard's worker count is derived from real heartbeats, and a crashed
worker disappears from it within ``TTL`` seconds without any cleanup.
"""

import logging
import socket
import threading
import time

import redis

from codeforge_core import keys

log = logging.getLogger(__name__)

TTL_S = 15
INTERVAL_S = 5


class Heartbeat(threading.Thread):
    def __init__(self, r: redis.Redis, worker_id: str, concurrency: int, stats: dict, stop: threading.Event):
        super().__init__(name="heartbeat", daemon=True)
        self.r = r
        self.worker_id = worker_id
        self.concurrency = concurrency
        self.stats = stats
        self.stop = stop
        self.started_at = int(time.time())

    def beat(self) -> None:
        key = keys.worker_key(self.worker_id)
        pipe = self.r.pipeline()
        pipe.hset(key, mapping={
            "worker_id": self.worker_id,
            "host": socket.gethostname(),
            "started_at": self.started_at,
            "last_seen": int(time.time()),
            "concurrency": self.concurrency,
            "busy": self.stats["busy"],
            "handled": self.stats["handled"],
        })
        pipe.expire(key, TTL_S)
        pipe.execute()

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                self.beat()
            except redis.RedisError as exc:
                log.warning("heartbeat failed", extra={"error": str(exc)})
            self.stop.wait(INTERVAL_S)
        try:
            self.r.delete(keys.worker_key(self.worker_id))
        except redis.RedisError:
            pass
