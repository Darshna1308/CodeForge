"""Queue consumer loop: scheduling, redelivery and dead-lettering.

Scheduling policy: interactive RUN jobs have strict priority over judged
SUBMIT jobs (a user is staring at the Run button), with an anti-starvation
rule — after ``RUN_BURST`` consecutive RUN jobs the consumer polls both
streams together, so a flood of runs cannot stall submissions indefinitely.
"""

import logging
import threading
import time

import redis
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from codeforge_core import events, keys
from codeforge_core import queue as cfqueue
from codeforge_core.config import Settings
from codeforge_core.enums import SubmissionStatus as S
from codeforge_core.repository import transition, utcnow

from . import metrics
from .processor import JobProcessor

log = logging.getLogger(__name__)

RUN_BURST = 4
AUTOCLAIM_EVERY_S = 15


class Consumer(threading.Thread):
    def __init__(self, index: int, settings: Settings, r: redis.Redis, sessions: sessionmaker[Session],
                 worker_id: str, stop: threading.Event, stats: dict):
        super().__init__(name=f"consumer-{index}", daemon=True)
        self.consumer_name = f"{worker_id}/{index}"
        self.settings = settings
        self.r = r
        self.sessions = sessions
        self.worker_id = worker_id
        self.stop = stop
        self.stats = stats
        self.processor = JobProcessor(settings, r, sessions, worker_id)
        self.run_streak = 0
        self.last_autoclaim = 0.0

    def run(self) -> None:
        backoff = 1.0
        while not self.stop.is_set():
            try:
                if time.monotonic() - self.last_autoclaim > AUTOCLAIM_EVERY_S:
                    self.last_autoclaim = time.monotonic()
                    self._recover_stuck_messages()
                for job in self._next_jobs():
                    self._handle_job(job)
                backoff = 1.0
            except redis.RedisError as exc:
                log.error("redis unavailable; backing off", extra={"error": str(exc), "backoff_s": backoff})
                self.stop.wait(backoff)
                backoff = min(backoff * 2, 15)
            except Exception:
                log.exception("unexpected consumer error")
                self.stop.wait(1)

    def _next_jobs(self) -> list[cfqueue.Job]:
        if self.run_streak < RUN_BURST:
            job = cfqueue.read(self.r, self.consumer_name, [keys.STREAM_RUN], block_ms=None)
            if job:
                self.run_streak += 1
                return [job]
        self.run_streak = 0
        # Blocking read across both streams; XREADGROUP may return one entry per stream.
        return cfqueue.read_many(self.r, self.consumer_name, [keys.STREAM_SUBMIT, keys.STREAM_RUN], block_ms=2000)

    def _handle_job(self, job: cfqueue.Job) -> None:
        metrics.BUSY.inc()
        self.stats["busy"] += 1
        try:
            outcome = self.processor.process(job)
        finally:
            metrics.BUSY.dec()
            self.stats["busy"] -= 1
        self.stats["handled"] += 1
        if outcome != "retry_later":
            cfqueue.ack(self.r, job)

    def _recover_stuck_messages(self) -> None:
        min_idle = self.settings.visibility_timeout_seconds * 1000
        for stream in (keys.STREAM_RUN, keys.STREAM_SUBMIT):
            for job in cfqueue.autoclaim(self.r, self.consumer_name, stream, min_idle):
                metrics.REDELIVERIES.inc()
                try:
                    self.r.incr(keys.COUNTER_REDELIVERED)
                except redis.RedisError:
                    pass
                if job.deliveries > self.settings.max_deliveries:
                    self._dead_letter(job)
                    continue
                log.warning("recovered pending message from a stalled consumer",
                            extra={"submission_id": job.submission_id, "deliveries": job.deliveries})
                self._handle_job(job)

    def _dead_letter(self, job: cfqueue.Job) -> None:
        metrics.DEAD_LETTERED.inc()
        log.error("poison message dead-lettered", extra={"submission_id": job.submission_id, "deliveries": job.deliveries})
        try:
            with self.sessions.begin() as s:
                row = transition(s, job.submission_id, S.INTERNAL_ERROR, actor=self.worker_id,
                                 values={"finished_at": utcnow(), "lease_expires_at": None,
                                         "error_message": "exceeded maximum deliveries"})
        except OperationalError:
            return  # keep it pending; retry on a later autoclaim
        cfqueue.dead_letter(self.r, job, "max_deliveries")
        if row is not None:
            events.publish(self.r, job.submission_id, "internal_error", reason="exceeded maximum deliveries")


