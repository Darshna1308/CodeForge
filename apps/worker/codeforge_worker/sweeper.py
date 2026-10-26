"""Leader-elected recovery loop ("sweeper").

Exactly one worker process at a time holds ``cf:lock:sweeper`` (SET NX PX with
a random token, renewed with a compare-and-renew Lua script). The leader
repairs the three ways a submission can get stuck:

1. **CREATED, never published** — the API committed the row but crashed or
   could not reach Redis before XADD. Publish, then flip to QUEUED (outbox relay).
2. **In progress, lease expired** — the owning worker died or hung. Mark the
   attempt ABANDONED and either re-queue (attempt < max) or fail it.
3. **QUEUED for too long** — the message was lost (e.g. Redis restarted without
   persistence). Publish again; duplicate messages are harmless.

All three are safe to run concurrently with live workers because every write
is a state-machine transition guarded by row locks and fencing tokens.
"""

import logging
import threading
import uuid
from datetime import timedelta

import redis
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from codeforge_core import events, keys
from codeforge_core import queue as cfqueue
from codeforge_core.config import Settings
from codeforge_core.enums import AttemptOutcome, SubmissionStatus as S
from codeforge_core.models import ExecutionAttempt, Submission
from codeforge_core.repository import transition, utcnow
from codeforge_core.state_machine import IN_PROGRESS

from . import metrics

log = logging.getLogger(__name__)

RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('pexpire', KEYS[1], ARGV[2])
end
return 0
"""


class Sweeper(threading.Thread):
    def __init__(self, settings: Settings, r: redis.Redis, sessions: sessionmaker[Session], worker_id: str, stop: threading.Event):
        super().__init__(name="sweeper", daemon=True)
        self.settings = settings
        self.r = r
        self.sessions = sessions
        self.worker_id = worker_id
        self.stop = stop
        self.token = uuid.uuid4().hex
        self.lock_ms = int(settings.sweeper_interval_seconds * 3 * 1000)
        self._renew = r.register_script(RENEW_SCRIPT)
        self.is_leader = False

    def run(self) -> None:
        while not self.stop.wait(self.settings.sweeper_interval_seconds):
            try:
                if self._acquire_or_renew():
                    self.sweep_once()
            except Exception:
                log.exception("sweeper iteration failed")

    def _acquire_or_renew(self) -> bool:
        if self.r.set(keys.SWEEPER_LOCK, self.token, nx=True, px=self.lock_ms):
            if not self.is_leader:
                log.info("acquired sweeper leadership")
            self.is_leader = True
        else:
            self.is_leader = bool(self._renew(keys=[keys.SWEEPER_LOCK], args=[self.token, self.lock_ms]))
        return self.is_leader

    def sweep_once(self) -> dict[str, int]:
        counts = {"published": 0, "requeued": 0, "failed": 0, "republished": 0}
        now = utcnow()
        actor = f"sweeper@{self.worker_id}"

        # 1. Outbox relay for rows the API never published.
        with self.sessions.begin() as s:
            stuck_created = s.execute(
                select(Submission.id, Submission.mode).where(
                    Submission.status == S.CREATED,
                    Submission.created_at < now - timedelta(seconds=self.settings.created_grace_seconds),
                ).limit(100)
            ).all()
        for sid, mode in stuck_created:
            cfqueue.enqueue(self.r, sid, mode)  # publish first: at-least-once
            with self.sessions.begin() as s:
                if transition(s, sid, S.QUEUED, actor=actor, expected_from={S.CREATED}, values={"queued_at": utcnow()}):
                    counts["published"] += 1
                    events.publish(self.r, sid, "queued", recovered=True)

        # 2. Expired leases: the owner is presumed dead.
        with self.sessions.begin() as s:
            expired = s.execute(
                select(Submission.id, Submission.mode, Submission.attempt, Submission.worker_id).where(
                    Submission.status.in_(IN_PROGRESS), Submission.lease_expires_at < now
                ).limit(100)
            ).all()
        for sid, mode, attempt, owner in expired:
            exhausted = attempt >= self.settings.max_attempts
            with self.sessions.begin() as s:
                target = S.INTERNAL_ERROR if exhausted else S.QUEUED
                values = {"lease_expires_at": None, "error_message": f"worker {owner} lease expired (attempt {attempt})"}
                values.update({"finished_at": utcnow()} if exhausted else {"queued_at": utcnow()})
                row = transition(s, sid, target, actor=actor, fence=(owner, attempt), values=values)
                if row is not None:
                    s.execute(
                        update(ExecutionAttempt)
                        .where(ExecutionAttempt.submission_id == sid, ExecutionAttempt.attempt_no == attempt,
                               ExecutionAttempt.outcome == AttemptOutcome.RUNNING)
                        .values(outcome=AttemptOutcome.ABANDONED, finished_at=utcnow(), error="lease expired")
                    )
            if row is None:
                continue
            log.warning("recovered submission from expired lease",
                        extra={"submission_id": sid, "owner": owner, "attempt": attempt, "action": target.value})
            if exhausted:
                counts["failed"] += 1
                events.publish(self.r, sid, "internal_error", reason="attempts exhausted after worker failures")
            else:
                counts["requeued"] += 1
                try:
                    cfqueue.enqueue(self.r, sid, mode)
                except redis.RedisError:
                    pass  # rule 3 will republish
                events.publish(self.r, sid, "retrying", attempt=attempt, reason="worker lease expired")

        # 3. QUEUED rows whose message was probably lost.
        stale_before = now - timedelta(seconds=self.settings.queued_stale_seconds)
        with self.sessions.begin() as s:
            stale = s.execute(
                update(Submission)
                .where(Submission.status == S.QUEUED, Submission.queued_at < stale_before)
                .values(queued_at=utcnow())
                .returning(Submission.id, Submission.mode)
            ).all()
        for sid, mode in stale:
            cfqueue.enqueue(self.r, sid, mode)
            counts["republished"] += 1

        for action, n in counts.items():
            if n:
                metrics.SWEEPER_ACTIONS.labels(action).inc(n)
        if any(counts.values()):
            log.info("sweeper pass", extra=counts)
        return counts
