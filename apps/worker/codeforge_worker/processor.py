"""Executes one queued job end to end: claim -> sandbox -> judge -> persist.

Correctness under concurrency rests on two mechanisms:

* **Claim CAS**: ``QUEUED -> PROCESSING`` succeeds for exactly one worker, so
  duplicate deliveries of the same message do no work.
* **Fencing token**: every later write is conditioned on
  ``(worker_id, attempt)``. If this worker stalls past its lease, the sweeper
  re-queues the submission, another worker claims it with ``attempt + 1``,
  and every write from the stale worker becomes a no-op.
"""

import logging
import time
from dataclasses import dataclass, field

import redis
from sqlalchemy import insert, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from codeforge_core import events, keys
from codeforge_core import logging as cflog
from codeforge_core import queue as cfqueue
from codeforge_core.config import Settings
from codeforge_core.enums import AttemptOutcome, SubmissionMode, SubmissionStatus as S, TestVerdict, Verdict
from codeforge_core.languages import get_language
from codeforge_core.models import ExecutionAttempt, Problem, Submission, SubmissionResult, TestCase
from codeforge_core.repository import lease_deadline, transition, utcnow

from . import metrics
from .judge import aggregate, judge_test
from .sandbox import SandboxError, SandboxSession

log = logging.getLogger(__name__)

STORED_OUTPUT_LIMIT = 8 * 1024


class LostLease(Exception):
    """This worker's fencing token is no longer valid; stop without writing."""


@dataclass
class TestSpec:
    ordinal: int
    test_case_id: int | None
    input: str
    expected: str | None
    is_sample: bool


@dataclass
class JobContext:
    submission_id: int
    attempt: int
    mode: SubmissionMode
    language: str
    source: str
    time_limit_ms: int
    memory_limit_mb: int
    tests: list[TestSpec] = field(default_factory=list)
    queue_wait_ms: int | None = None


class JobProcessor:
    def __init__(self, settings: Settings, r: redis.Redis, sessions: sessionmaker[Session], worker_id: str):
        self.settings = settings
        self.r = r
        self.sessions = sessions
        self.worker_id = worker_id

    # ------------------------------------------------------------------ public
    def process(self, job: cfqueue.Job) -> str:
        """Returns an outcome label. ``retry_later`` means: do not ACK."""
        token = cflog.bind(submission_id=job.submission_id, stream=job.stream, message_id=job.message_id)
        try:
            try:
                ctx = self._claim(job)
            except OperationalError as exc:
                log.error("database unavailable during claim; leaving message pending", extra={"error": str(exc)[:200]})
                return "retry_later"
            if ctx is None:
                metrics.DUPLICATES.inc()
                self._incr(keys.COUNTER_DUPLICATES)
                log.info("duplicate or stale delivery skipped")
                return "duplicate"
            cflog.bind(attempt=ctx.attempt)
            return self._execute(ctx)
        finally:
            cflog.reset(token)

    # ------------------------------------------------------------------- claim
    def _claim(self, job: cfqueue.Job) -> JobContext | None:
        with self.sessions.begin() as s:
            row = self._try_claim(s, job.submission_id)
            if row is None:
                current = s.execute(select(Submission.status).where(Submission.id == job.submission_id)).scalar_one_or_none()
                if current == S.CREATED:
                    # Outbox case: the API published the message but has not
                    # flipped CREATED -> QUEUED yet. The message proves it was
                    # published, so complete the flip on its behalf.
                    transition(s, job.submission_id, S.QUEUED, actor=self.worker_id, values={"queued_at": utcnow()})
                    row = self._try_claim(s, job.submission_id)
            if row is None:
                return None

            queue_wait_ms = int((time.time() * 1000) - job.enqueued_at_ms) if job.enqueued_at_ms else None
            s.execute(
                insert(ExecutionAttempt).values(
                    submission_id=row.id, attempt_no=row.attempt, worker_id=self.worker_id,
                    outcome=AttemptOutcome.RUNNING, queue_wait_ms=queue_wait_ms,
                )
            )
            problem = s.get(Problem, row.problem_id)
            ctx = JobContext(
                submission_id=row.id, attempt=row.attempt, mode=row.mode, language=row.language,
                source=row.source_code, time_limit_ms=problem.time_limit_ms,
                memory_limit_mb=problem.memory_limit_mb, queue_wait_ms=queue_wait_ms,
            )
            if row.mode == SubmissionMode.RUN and row.custom_input is not None:
                ctx.tests = [TestSpec(1, None, row.custom_input, None, False)]
            else:
                q = select(TestCase).where(TestCase.problem_id == row.problem_id).order_by(TestCase.ordinal)
                if row.mode == SubmissionMode.RUN:
                    q = q.where(TestCase.is_sample.is_(True))
                ctx.tests = [
                    TestSpec(i + 1, tc.id, tc.input, tc.expected_output, tc.is_sample)
                    for i, tc in enumerate(s.execute(q).scalars())
                ]
        if queue_wait_ms is not None:
            metrics.QUEUE_WAIT_SECONDS.observe(max(queue_wait_ms, 0) / 1000)
        self._publish(ctx, "claimed", worker_id=self.worker_id, attempt=ctx.attempt, queue_wait_ms=queue_wait_ms, tests=len(ctx.tests))
        log.info("job claimed", extra={"tests": len(ctx.tests), "language": ctx.language, "mode": ctx.mode.value})
        return ctx

    def _try_claim(self, s: Session, submission_id: int) -> Submission | None:
        return transition(
            s, submission_id, S.PROCESSING, actor=self.worker_id, expected_from={S.QUEUED},
            values={
                "worker_id": self.worker_id,
                "attempt": Submission.attempt + 1,
                "lease_expires_at": lease_deadline(self.settings.lease_seconds),
                "started_at": utcnow(),
            },
        )

    # ----------------------------------------------------------------- execute
    def _execute(self, ctx: JobContext) -> str:
        started = time.monotonic()
        lang = get_language(ctx.language)
        fence = (self.worker_id, ctx.attempt)
        sandbox_ms = compile_ms = None
        try:
            with SandboxSession(self.settings, lang, ctx.submission_id, ctx.attempt, ctx.memory_limit_mb) as sbx:
                sandbox_ms = sbx.startup_ms
                metrics.SANDBOX_START_SECONDS.observe(sandbox_ms / 1000)
                self._publish(ctx, "sandbox_ready", ms=sandbox_ms, container=sbx.name)

                if lang.compile_argv:
                    self._move(ctx, S.COMPILING)
                    self._publish(ctx, "compiling")
                comp = sbx.compile(ctx.source, ctx.time_limit_ms)
                if not comp.skipped:
                    compile_ms = comp.ms
                    metrics.COMPILE_SECONDS.observe(comp.ms / 1000)
                    self._publish(ctx, "compiled", ok=comp.ok, ms=comp.ms)
                if not comp.ok:
                    self._finish(ctx, Verdict.COMPILATION_ERROR, [], compile_ms=comp.ms, compile_output=comp.output,
                                 sandbox_ms=sandbox_ms, started=started)
                    return "completed"

                self._move(ctx, S.RUNNING)
                self._publish(ctx, "running", tests=len(ctx.tests))
                results: list[dict] = []
                stop = False
                for t in ctx.tests:
                    if stop:
                        results.append({"spec": t, "verdict": TestVerdict.SKIPPED, "raw": None})
                        continue
                    raw = sbx.run(t.ordinal, t.input, ctx.time_limit_ms,
                              expected_size=len(t.expected.encode()) if t.expected is not None else None)
                    verdict = judge_test(raw, t.expected)
                    results.append({"spec": t, "verdict": verdict, "raw": raw})
                    self._publish(
                        ctx, "test", index=t.ordinal, verdict=verdict.value, cpu_ms=raw.get("cpu_ms"),
                        wall_ms=raw.get("wall_ms"), memory_kb=raw.get("max_rss_kb"), sample=t.is_sample,
                    )
                    self._renew_lease(ctx)
                    # Judged submissions stop at the first failing test, like most judges.
                    if ctx.mode == SubmissionMode.SUBMIT and verdict != TestVerdict.ACCEPTED:
                        stop = True

            self._move(ctx, S.JUDGING)
            final = aggregate([r["verdict"] for r in results])
            self._publish(ctx, "judging")
            self._finish(ctx, final, results, compile_ms=compile_ms, compile_output=None, sandbox_ms=sandbox_ms, started=started)
            return "completed"
        except LostLease:
            log.warning("lost lease; abandoning job without writing results")
            self._mark_attempt(ctx, AttemptOutcome.LOST_LEASE, "fenced out by a newer attempt", started, sandbox_ms, compile_ms)
            metrics.JOBS.labels("lost_lease").inc()
            return "lost_lease"
        except OperationalError as exc:
            log.error("database error mid-job; leaving message pending for recovery", extra={"error": str(exc)[:200]})
            metrics.JOBS.labels("db_error").inc()
            return "retry_later"
        except Exception as exc:  # SandboxError or anything unexpected: infrastructure failure
            metrics.SANDBOX_FAILURES.inc()
            log.exception("job failed with infrastructure error")
            return self._fail_attempt(ctx, exc, started, sandbox_ms, compile_ms)
        finally:
            metrics.JOB_SECONDS.observe(time.monotonic() - started)

    # ------------------------------------------------------------ transitions
    def _move(self, ctx: JobContext, to: S) -> None:
        with self.sessions.begin() as s:
            row = transition(
                s, ctx.submission_id, to, actor=self.worker_id, fence=(self.worker_id, ctx.attempt),
                values={"lease_expires_at": lease_deadline(self.settings.lease_seconds)},
            )
        if row is None:
            raise LostLease()
        self._publish(ctx, "status", status=to.value)

    def _renew_lease(self, ctx: JobContext) -> None:
        with self.sessions.begin() as s:
            n = s.execute(
                update(Submission)
                .where(Submission.id == ctx.submission_id, Submission.worker_id == self.worker_id,
                       Submission.attempt == ctx.attempt, Submission.status.in_([S.PROCESSING, S.COMPILING, S.RUNNING, S.JUDGING]))
                .values(lease_expires_at=lease_deadline(self.settings.lease_seconds))
            ).rowcount
        if n == 0:
            raise LostLease()

    def _finish(self, ctx: JobContext, verdict: Verdict, results: list[dict], *, compile_ms, compile_output, sandbox_ms, started) -> None:
        executed = [r for r in results if r["raw"] is not None]
        cpu_values = [r["raw"]["cpu_ms"] for r in executed if r["raw"].get("cpu_ms") is not None]
        mem_values = [r["raw"]["max_rss_kb"] for r in executed if r["raw"].get("max_rss_kb") is not None]
        passed = sum(1 for r in results if r["verdict"] in (TestVerdict.ACCEPTED, TestVerdict.EXECUTED))
        runtime_ms = max(cpu_values) if cpu_values else None
        memory_kb = max(mem_values) if mem_values else None
        total_ms = int((time.monotonic() - started) * 1000)

        with self.sessions.begin() as s:
            row = transition(
                s, ctx.submission_id, S.COMPLETED, actor=self.worker_id, fence=(self.worker_id, ctx.attempt),
                values={
                    "verdict": verdict, "finished_at": utcnow(), "lease_expires_at": None,
                    "runtime_ms": runtime_ms, "memory_kb": memory_kb, "compile_ms": compile_ms,
                    "tests_passed": passed, "tests_total": len(ctx.tests),
                    "compile_output": (compile_output or None) and compile_output[:16384],
                },
            )
            if row is None:
                raise LostLease()  # rolls back: nothing from this attempt is persisted
            # Results are replaced per attempt so a retried job never mixes attempts.
            s.query(SubmissionResult).filter(SubmissionResult.submission_id == ctx.submission_id).delete()
            for r in results:
                spec: TestSpec = r["spec"]
                raw = r["raw"] or {}
                # Program output is only kept where the test data is public anyway:
                # RUN mode (samples / the user's own input) or sample tests. Never
                # for hidden tests, where stdout/stderr could echo hidden input.
                expose = ctx.mode == SubmissionMode.RUN or spec.is_sample
                s.add(SubmissionResult(
                    submission_id=ctx.submission_id, test_case_id=spec.test_case_id, ordinal=spec.ordinal,
                    verdict=r["verdict"], cpu_ms=raw.get("cpu_ms"), wall_ms=raw.get("wall_ms"),
                    memory_kb=raw.get("max_rss_kb"), exit_code=raw.get("exit_code"), signal=raw.get("signal"),
                    stdout=raw.get("stdout", "")[:STORED_OUTPUT_LIMIT] if expose and raw else None,
                    stderr=raw.get("stderr", "")[:STORED_OUTPUT_LIMIT] if expose and raw else None,
                ))
            s.execute(
                update(ExecutionAttempt)
                .where(ExecutionAttempt.submission_id == ctx.submission_id, ExecutionAttempt.attempt_no == ctx.attempt)
                .values(outcome=AttemptOutcome.SUCCEEDED, finished_at=utcnow(), sandbox_start_ms=sandbox_ms,
                        compile_ms=compile_ms, total_ms=total_ms)
            )

        metrics.JOBS.labels("completed").inc()
        metrics.VERDICTS.labels(verdict.value, ctx.language, ctx.mode.value).inc()
        self._incr(keys.COUNTER_JOBS_COMPLETED)
        self._publish(
            ctx, "completed", verdict=verdict.value, runtime_ms=runtime_ms, memory_kb=memory_kb,
            passed=passed, total=len(ctx.tests), total_ms=total_ms,
        )
        log.info("job completed", extra={"verdict": verdict.value, "duration_ms": total_ms, "runtime_ms": runtime_ms})

    def _fail_attempt(self, ctx: JobContext, exc: Exception, started, sandbox_ms, compile_ms) -> str:
        message = str(exc)[:500] if isinstance(exc, SandboxError) else f"{type(exc).__name__}: internal error"
        self._mark_attempt(ctx, AttemptOutcome.FAILED, message, started, sandbox_ms, compile_ms)
        self._incr(keys.COUNTER_JOBS_FAILED)
        fence = (self.worker_id, ctx.attempt)
        try:
            with self.sessions.begin() as s:
                if ctx.attempt < self.settings.max_attempts:
                    row = transition(s, ctx.submission_id, S.QUEUED, actor=self.worker_id, fence=fence,
                                     values={"lease_expires_at": None, "queued_at": utcnow(), "error_message": message})
                    outcome = "requeued"
                else:
                    row = transition(s, ctx.submission_id, S.INTERNAL_ERROR, actor=self.worker_id, fence=fence,
                                     values={"lease_expires_at": None, "finished_at": utcnow(), "error_message": message})
                    outcome = "internal_error"
        except OperationalError:
            return "retry_later"
        if row is None:
            return "lost_lease"
        metrics.JOBS.labels(outcome).inc()
        if outcome == "requeued":
            # Exponential backoff before the retry becomes visible to workers.
            time.sleep(min(2 ** ctx.attempt, 10))
            try:
                cfqueue.enqueue(self.r, ctx.submission_id, ctx.mode)
            except redis.RedisError:
                log.warning("re-enqueue failed; sweeper will recover the QUEUED row")
            self._publish(ctx, "retrying", attempt=ctx.attempt, reason=message)
        else:
            self._publish(ctx, "internal_error", reason=message)
        return outcome

    def _mark_attempt(self, ctx, outcome: AttemptOutcome, error: str | None, started, sandbox_ms, compile_ms) -> None:
        try:
            with self.sessions.begin() as s:
                s.execute(
                    update(ExecutionAttempt)
                    .where(ExecutionAttempt.submission_id == ctx.submission_id, ExecutionAttempt.attempt_no == ctx.attempt)
                    .values(outcome=outcome, error=error, finished_at=utcnow(), sandbox_start_ms=sandbox_ms,
                            compile_ms=compile_ms, total_ms=int((time.monotonic() - started) * 1000))
                )
        except OperationalError:
            log.warning("could not record attempt outcome (database unavailable)")

    # ----------------------------------------------------------------- helpers
    def _publish(self, ctx: JobContext, event_type: str, **data) -> None:
        events.publish(self.r, ctx.submission_id, event_type, **data)

    def _incr(self, key: str) -> None:
        try:
            self.r.incr(key)
        except redis.RedisError:
            pass
