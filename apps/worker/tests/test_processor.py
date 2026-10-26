"""Worker job processing against real Postgres, Redis and Docker."""

import time
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from codeforge_core import keys
from codeforge_core import queue as cfqueue
from codeforge_core.config import get_settings
from codeforge_core.db import get_sessionmaker
from codeforge_core.enums import AttemptOutcome, SubmissionMode, SubmissionStatus as S, Verdict
from codeforge_core.models import ExecutionAttempt, Problem, Submission, User
from codeforge_core.redis_client import get_redis
from codeforge_core.repository import transition, utcnow
from codeforge_worker.processor import JobProcessor
from codeforge_worker.sweeper import Sweeper

from worker_helpers import requires_docker

TWO_SUM = (
    "import sys\nd = sys.stdin.read().split()\nn, t = int(d[0]), int(d[1])\nseen = {}\n"
    "for j in range(n):\n    x = int(d[2 + j])\n    if t - x in seen:\n        print(seen[t - x], j); break\n    seen.setdefault(x, j)\n"
)


def make_submission(source=TWO_SUM, status=S.QUEUED, mode=SubmissionMode.SUBMIT) -> int:
    with get_sessionmaker().begin() as s:
        user = s.execute(select(User).where(User.username == "worker_test")).scalar_one_or_none()
        if user is None:
            user = User(username="worker_test", email="worker_test@example.com", password_hash="x")
            s.add(user)
            s.flush()
        pid = s.execute(select(Problem.id).where(Problem.slug == "two-sum")).scalar_one()
        sub = Submission(user_id=user.id, problem_id=pid, language="python", mode=mode, source_code=source,
                         status=status, queued_at=utcnow())
        s.add(sub)
        s.flush()
        return sub.id


def job_for(sid: int) -> cfqueue.Job:
    return cfqueue.Job(stream=keys.STREAM_SUBMIT, message_id="0-1", submission_id=sid, enqueued_at_ms=int(time.time() * 1000))


def processor(worker_id="test-worker") -> JobProcessor:
    return JobProcessor(get_settings(), get_redis(), get_sessionmaker(), worker_id)


def get(sid: int) -> Submission:
    with get_sessionmaker()() as s:
        return s.get(Submission, sid)


@requires_docker
def test_accepted_end_to_end_and_duplicate_delivery_is_noop():
    sid = make_submission()
    assert processor("w1").process(job_for(sid)) == "completed"
    sub = get(sid)
    assert sub.status == S.COMPLETED and sub.verdict == Verdict.ACCEPTED and sub.attempt == 1
    assert sub.tests_passed == sub.tests_total
    # Same message delivered again (at-least-once): no second execution.
    assert processor("w2").process(job_for(sid)) == "duplicate"
    with get_sessionmaker()() as s:
        attempts = s.execute(select(ExecutionAttempt).where(ExecutionAttempt.submission_id == sid)).scalars().all()
    assert len(attempts) == 1 and attempts[0].outcome == AttemptOutcome.SUCCEEDED


@requires_docker
def test_wrong_answer_skips_remaining_tests():
    sid = make_submission(source="print('0 1')\n")
    processor().process(job_for(sid))
    sub = get(sid)
    assert sub.verdict == Verdict.WRONG_ANSWER
    with get_sessionmaker()() as s:
        verdicts = [r.verdict.value for r in s.get(Submission, sid).results]
    first_bad = next(i for i, v in enumerate(verdicts) if v != "ACCEPTED")
    assert set(verdicts[first_bad + 1:]) <= {"SKIPPED"}


@requires_docker
def test_message_for_created_row_completes_outbox_flip():
    sid = make_submission(status=S.CREATED)
    assert processor().process(job_for(sid)) == "completed"
    assert get(sid).status == S.COMPLETED


def test_sandbox_failure_requeues_then_fails_after_max_attempts(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "sandbox_image", "codeforge-image-that-does-not-exist:never")
    monkeypatch.setattr("codeforge_worker.processor.time.sleep", lambda s: None)
    sid = make_submission()
    p = processor()
    outcomes = [p.process(job_for(sid)) for _ in range(settings.max_attempts)]
    assert outcomes == ["requeued"] * (settings.max_attempts - 1) + ["internal_error"]
    sub = get(sid)
    assert sub.status == S.INTERNAL_ERROR and sub.attempt == settings.max_attempts and sub.verdict is None


def _sweeper() -> Sweeper:
    import threading
    return Sweeper(get_settings(), get_redis(), get_sessionmaker(), "sweeper-test", threading.Event())


def test_sweeper_requeues_expired_lease_and_fences_old_worker():
    sid = make_submission()
    with get_sessionmaker().begin() as s:
        transition(s, sid, S.PROCESSING, actor="dead", values={"worker_id": "dead", "attempt": 1,
                                                                "lease_expires_at": utcnow() - timedelta(seconds=1)})
        s.add(ExecutionAttempt(submission_id=sid, attempt_no=1, worker_id="dead", outcome=AttemptOutcome.RUNNING))
    counts = _sweeper().sweep_once()
    assert counts["requeued"] >= 1
    sub = get(sid)
    assert sub.status == S.QUEUED and sub.lease_expires_at is None
    with get_sessionmaker()() as s:
        a = s.execute(select(ExecutionAttempt).where(ExecutionAttempt.submission_id == sid)).scalar_one()
    assert a.outcome == AttemptOutcome.ABANDONED
    # The "dead" worker was merely slow and now tries to report: fenced out.
    with get_sessionmaker().begin() as s:
        assert transition(s, sid, S.RUNNING, actor="dead", fence=("dead", 1)) is None


def test_sweeper_fails_submission_when_attempts_exhausted():
    sid = make_submission()
    with get_sessionmaker().begin() as s:
        transition(s, sid, S.PROCESSING, actor="dead", values={"worker_id": "dead", "attempt": get_settings().max_attempts,
                                                                "lease_expires_at": utcnow() - timedelta(seconds=1)})
    _sweeper().sweep_once()
    assert get(sid).status == S.INTERNAL_ERROR


def test_sweeper_publishes_stuck_created_rows():
    sid = make_submission(status=S.CREATED)
    with get_sessionmaker().begin() as s:
        s.execute(update(Submission).where(Submission.id == sid).values(created_at=utcnow() - timedelta(minutes=5)))
    before = get_redis().xlen(keys.STREAM_SUBMIT)
    _sweeper().sweep_once()
    assert get(sid).status == S.QUEUED
    assert get_redis().xlen(keys.STREAM_SUBMIT) > before


def test_sweeper_leader_election_single_holder():
    get_redis().delete(keys.SWEEPER_LOCK)
    a, b = _sweeper(), _sweeper()
    assert a._acquire_or_renew() is True
    assert b._acquire_or_renew() is False
    assert a._acquire_or_renew() is True  # renewal by the holder
