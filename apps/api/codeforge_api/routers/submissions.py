"""Submission + execution endpoints and the SSE realtime gateway."""

import asyncio
import json
import logging
import time

import redis
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from codeforge_core import events, keys
from codeforge_core import queue as cfqueue
from codeforge_core.config import get_settings
from codeforge_core.db import get_sessionmaker
from codeforge_core.enums import SubmissionMode, SubmissionStatus as S
from codeforge_core.languages import LANGUAGES
from codeforge_core.models import (
    ExecutionAttempt, Language, Problem, Submission, SubmissionResult, SubmissionTransition, TestCase, User,
)
from codeforge_core.repository import transition, utcnow
from codeforge_core.state_machine import TERMINAL

from ..deps import get_current_user, get_db, get_r
from ..errors import APIError
from ..metrics import ENQUEUE_FAILURES, SSE_CONNECTIONS, SUBMISSIONS_CREATED
from ..ratelimit import limit_user
from ..schemas import (
    AttemptOut, ExecutionCreate, Page, SubmissionAccepted, SubmissionCreate, SubmissionDetail, SubmissionOut,
    TestResultOut, TransitionOut,
)

log = logging.getLogger(__name__)
router = APIRouter(tags=["submissions"])

TERMINAL_EVENTS = {"completed", "internal_error", "cancelled"}


def display_id(submission_id: int) -> str:
    return f"CF-{submission_id}"


def _accepted(sub: Submission, replay: bool = False) -> SubmissionAccepted:
    return SubmissionAccepted(
        id=sub.id, display_id=display_id(sub.id), status=sub.status, mode=sub.mode,
        events_url=f"/submissions/{sub.id}/events", detail_url=f"/submissions/{sub.id}", idempotent_replay=replay,
    )


def _create(
    db: Session, r: redis.Redis, user: User, body: SubmissionCreate, mode: SubmissionMode,
    custom_input: str | None, idempotency_key: str | None, response: Response,
) -> SubmissionAccepted:
    s = get_settings()
    if len(body.source_code.encode("utf-8")) > s.max_source_bytes:
        raise APIError(413, "payload_too_large", f"Source code exceeds {s.max_source_bytes} bytes")
    if custom_input is not None and len(custom_input.encode("utf-8")) > s.max_custom_input_bytes:
        raise APIError(413, "payload_too_large", f"Custom input exceeds {s.max_custom_input_bytes} bytes")
    if body.language not in LANGUAGES or not db.get(Language, body.language) or not db.get(Language, body.language).enabled:
        raise APIError(422, "unsupported_language", f"Language '{body.language}' is not supported",
                       details={"supported": sorted(LANGUAGES)})
    problem = db.execute(select(Problem).where(Problem.slug == body.problem_slug, Problem.is_published.is_(True))).scalar_one_or_none()
    if problem is None:
        raise APIError(404, "not_found", f"Problem '{body.problem_slug}' not found")

    # 1. Persist (state CREATED). The row acts as a transactional outbox entry.
    sub = Submission(
        user_id=user.id, problem_id=problem.id, language=body.language, mode=mode,
        source_code=body.source_code, custom_input=custom_input, idempotency_key=idempotency_key,
        status=S.CREATED,
    )
    db.add(sub)
    try:
        db.flush()
        db.add(SubmissionTransition(submission_id=sub.id, from_status=None, to_status=S.CREATED, attempt=0, actor="api"))
        db.commit()
    except IntegrityError:
        db.rollback()
        if idempotency_key is None:
            raise
        # Same (user, Idempotency-Key) already exists: return the original instead of a duplicate.
        existing = db.execute(
            select(Submission).where(Submission.user_id == user.id, Submission.idempotency_key == idempotency_key)
        ).scalar_one()
        response.status_code = status.HTTP_200_OK
        return _accepted(existing, replay=True)

    SUBMISSIONS_CREATED.labels(mode.value, body.language).inc()
    # 2. Publish to the queue, 3. flip CREATED -> QUEUED. If Redis is down the
    # row stays CREATED and the worker-side sweeper publishes it later.
    try:
        cfqueue.enqueue(r, sub.id, mode)
    except redis.RedisError as exc:
        ENQUEUE_FAILURES.inc()
        log.warning("enqueue failed; sweeper will publish", extra={"submission_id": sub.id, "error": str(exc)})
        return _accepted(sub)
    row = transition(db, sub.id, S.QUEUED, actor="api", expected_from={S.CREATED}, values={"queued_at": utcnow()})
    db.commit()
    events.publish(r, sub.id, "queued", mode=mode.value, language=body.language)
    if row is not None:
        sub.status = row.status
    else:
        db.refresh(sub)  # a fast worker already moved it on
    log.info("submission accepted", extra={"submission_id": sub.id, "mode": mode.value, "language": body.language})
    return _accepted(sub)


def _idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not (8 <= len(value) <= 64) or not all(c.isalnum() or c in "-_" for c in value):
        raise APIError(422, "invalid_idempotency_key", "Idempotency-Key must be 8-64 chars of [A-Za-z0-9_-]")
    return value


@router.post("/submissions", response_model=SubmissionAccepted, status_code=status.HTTP_202_ACCEPTED)
def create_submission(
    body: SubmissionCreate,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(limit_user("submit", "rate_limit_submit")),
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_r),
):
    """Judge against all tests (samples + hidden). Returns immediately with the submission id."""
    return _create(db, r, user, body, SubmissionMode.SUBMIT, None, _idempotency_key(idempotency_key), response)


@router.post("/executions", response_model=SubmissionAccepted, status_code=status.HTTP_202_ACCEPTED)
def create_execution(
    body: ExecutionCreate,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(limit_user("run", "rate_limit_run")),
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_r),
):
    """"Run Code": sample tests, or the given custom input. Never touches hidden tests."""
    return _create(db, r, user, body, SubmissionMode.RUN, body.custom_input, _idempotency_key(idempotency_key), response)


def _summary(sub: Submission, problem: Problem) -> dict:
    return dict(
        id=sub.id, display_id=display_id(sub.id), problem_slug=problem.slug, problem_title=problem.title,
        language=sub.language, mode=sub.mode, status=sub.status, verdict=sub.verdict, runtime_ms=sub.runtime_ms,
        memory_kb=sub.memory_kb, tests_passed=sub.tests_passed, tests_total=sub.tests_total, attempt=sub.attempt,
        created_at=sub.created_at, finished_at=sub.finished_at,
    )


@router.get("/submissions", response_model=Page[SubmissionOut])
def list_submissions(
    problem: str | None = Query(default=None, max_length=80),
    include_runs: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The caller's own submission history, newest first (uses ix_submissions_user_created)."""
    q = select(Submission, Problem).join(Problem, Problem.id == Submission.problem_id).where(Submission.user_id == user.id)
    if not include_runs:
        q = q.where(Submission.mode == SubmissionMode.SUBMIT)
    if problem:
        q = q.where(Problem.slug == problem)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(q.order_by(Submission.created_at.desc(), Submission.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[SubmissionOut(**_summary(sub, p)) for sub, p in rows], total=total, page=page, page_size=page_size)


def _owned(db: Session, user: User, submission_id: int) -> Submission:
    sub = db.get(Submission, submission_id)
    # 404 (not 403) for other users' submissions: do not confirm that an id exists.
    if sub is None or (sub.user_id != user.id and user.role.value != "ADMIN"):
        raise APIError(404, "not_found", "Submission not found")
    return sub


def build_detail(db: Session, sub: Submission) -> SubmissionDetail:
    problem = db.get(Problem, sub.problem_id)
    rows = db.execute(
        select(SubmissionResult, TestCase.is_sample, TestCase.input, TestCase.expected_output)
        .outerjoin(TestCase, TestCase.id == SubmissionResult.test_case_id)
        .where(SubmissionResult.submission_id == sub.id)
        .order_by(SubmissionResult.ordinal)
    ).all()
    results = []
    for res, is_sample, tc_input, tc_expected in rows:
        public = bool(is_sample)
        custom = res.test_case_id is None and sub.mode == SubmissionMode.RUN
        results.append(TestResultOut(
            ordinal=res.ordinal, verdict=res.verdict, is_sample=public, cpu_ms=res.cpu_ms, wall_ms=res.wall_ms,
            memory_kb=res.memory_kb, exit_code=res.exit_code, signal=res.signal,
            input=tc_input if public else (sub.custom_input if custom else None),
            expected_output=tc_expected if public else None,
            stdout=res.stdout, stderr=res.stderr,
        ))
    attempts = db.execute(
        select(ExecutionAttempt).where(ExecutionAttempt.submission_id == sub.id).order_by(ExecutionAttempt.attempt_no)
    ).scalars().all()
    transitions = db.execute(
        select(SubmissionTransition).where(SubmissionTransition.submission_id == sub.id).order_by(SubmissionTransition.id)
    ).scalars().all()
    return SubmissionDetail(
        **_summary(sub, problem),
        source_code=sub.source_code, custom_input=sub.custom_input, compile_output=sub.compile_output,
        compile_ms=sub.compile_ms, error_message=sub.error_message, worker_id=sub.worker_id,
        queued_at=sub.queued_at, started_at=sub.started_at, results=results,
        attempts=[AttemptOut(attempt_no=a.attempt_no, worker_id=a.worker_id, outcome=a.outcome.value, started_at=a.started_at,
                             finished_at=a.finished_at, queue_wait_ms=a.queue_wait_ms, sandbox_start_ms=a.sandbox_start_ms,
                             compile_ms=a.compile_ms, total_ms=a.total_ms, error=a.error) for a in attempts],
        transitions=[TransitionOut(from_status=t.from_status, to_status=t.to_status, attempt=t.attempt, actor=t.actor, at=t.at)
                     for t in transitions],
    )


@router.get("/submissions/{submission_id}", response_model=SubmissionDetail)
@router.get("/executions/{submission_id}", response_model=SubmissionDetail, include_in_schema=False)
def get_submission(submission_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return build_detail(db, _owned(db, user, submission_id))


@router.post("/submissions/{submission_id}/cancel", response_model=SubmissionOut)
def cancel_submission(submission_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db),
                      r: redis.Redis = Depends(get_r)):
    """Cancel before a worker claims it. Racing a worker's claim is resolved by the row lock."""
    sub = _owned(db, user, submission_id)
    row = transition(db, sub.id, S.CANCELLED, actor=f"user:{user.id}", expected_from={S.CREATED, S.QUEUED},
                     values={"finished_at": utcnow()})
    if row is None:
        db.rollback()
        raise APIError(409, "conflict", "Submission can no longer be cancelled", details={"status": sub.status.value})
    db.commit()
    events.publish(r, sub.id, "cancelled")
    db.refresh(sub)
    return SubmissionOut(**_summary(sub, db.get(Problem, sub.problem_id)))


# ----------------------------------------------------------------- realtime (SSE)
def _sse(event: str, data: dict, event_id: str | None = None) -> str:
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, default=str)}")
    return "\n".join(lines) + "\n\n"


def _snapshot(submission_id: int) -> dict:
    with get_sessionmaker()() as db:
        sub = db.get(Submission, submission_id)
        detail = build_detail(db, sub)
        return json.loads(detail.model_dump_json(exclude={"source_code", "custom_input", "transitions"}))


_aioredis: aioredis.Redis | None = None


def _async_redis() -> aioredis.Redis:
    global _aioredis
    if _aioredis is None:
        _aioredis = aioredis.Redis.from_url(get_settings().redis_url, decode_responses=True, socket_connect_timeout=2)
    return _aioredis


@router.get("/submissions/{submission_id}/events")
async def submission_events(
    submission_id: int,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Server-Sent Events stream of lifecycle events for one submission.

    * Starts with a ``snapshot`` (authoritative DB state), then replays the
      submission's Redis Stream from the beginning (or from ``Last-Event-ID``
      when the browser reconnects), then tails it with XREAD BLOCK.
    * Heartbeat comments every 15s keep proxies from closing idle connections.
    * Closes after a terminal event, after 10 minutes, or when the client leaves.
    * If Redis is unavailable it degrades to polling Postgres once a second.
    """
    await run_in_threadpool(_owned, db, user, submission_id)
    db.close()  # do not hold a pooled connection for the lifetime of the stream
    SSE_CONNECTIONS.inc()
    stream_key = keys.submission_events(submission_id)
    start_id = last_event_id if last_event_id and all(c.isdigit() or c == "-" for c in last_event_id) else "0-0"

    async def gen():
        snap = await run_in_threadpool(_snapshot, submission_id)
        yield "retry: 2000\n\n"
        yield _sse("snapshot", snap)
        r = _async_redis()
        if S(snap["status"]) in TERMINAL:
            # Already finished: replay whatever timeline is still retained, then close.
            try:
                for entry_id, fields in await r.xrange(stream_key, min="-" if start_id == "0-0" else f"({start_id}"):
                    evt = events.decode(fields)
                    yield _sse(evt["type"], evt, entry_id)
            except (redis.RedisError, OSError):
                pass
            yield _sse("end", {})
            return
        last = start_id
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            if await request.is_disconnected():
                return
            try:
                resp = await r.xread({stream_key: last}, block=15000, count=100)
            except (redis.RedisError, OSError):
                # Degraded mode: poll the database for status changes.
                await asyncio.sleep(1)
                snap = await run_in_threadpool(_snapshot, submission_id)
                yield _sse("snapshot", snap)
                if S(snap["status"]) in TERMINAL:
                    return
                continue
            if not resp:
                if S((await run_in_threadpool(_snapshot, submission_id))["status"]) in TERMINAL:
                    yield _sse("end", {})
                    return
                yield ": heartbeat\n\n"
                continue
            for _stream, entries in resp:
                for entry_id, fields in entries:
                    last = entry_id
                    evt = events.decode(fields)
                    yield _sse(evt["type"], evt, entry_id)
                    if evt["type"] in TERMINAL_EVENTS:
                        yield _sse("snapshot", await run_in_threadpool(_snapshot, submission_id))
                        yield _sse("end", {})
                        return

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
