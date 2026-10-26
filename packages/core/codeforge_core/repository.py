"""Transactional persistence helpers for the submission state machine."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from .enums import SubmissionStatus
from .models import Submission, SubmissionTransition
from .state_machine import can_transition


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def lease_deadline(seconds: int) -> datetime:
    return utcnow() + timedelta(seconds=seconds)


def transition(
    session: Session,
    submission_id: int,
    to: SubmissionStatus,
    *,
    actor: str,
    expected_from: set[SubmissionStatus] | frozenset[SubmissionStatus] | None = None,
    fence: tuple[str, int] | None = None,
    values: dict[str, Any] | None = None,
) -> Submission | None:
    """Move a submission to ``to`` if, and only if, that is legal *right now*.

    1. ``SELECT ... FOR UPDATE`` takes the row lock. Concurrent callers (two
       workers that received the same message, the sweeper, a cancel request)
       queue up behind it; under READ COMMITTED each one re-reads the latest
       committed row once the lock is released.
    2. The current status is checked against the state machine table and the
       caller's ``expected_from`` set; the (worker_id, attempt) fencing token
       is checked when given.
    3. The guarded UPDATE and the audit row are written in the same transaction.

    Returns the updated row, or ``None`` if the transition is not (or no
    longer) applicable. Callers treat ``None`` as "someone else won".
    """
    current = session.execute(
        select(Submission.status, Submission.worker_id, Submission.attempt)
        .where(Submission.id == submission_id)
        .with_for_update()
    ).one_or_none()
    if current is None:
        return None
    status, worker_id, attempt = current
    if not can_transition(status, to):
        return None
    if expected_from is not None and status not in expected_from:
        return None
    if fence is not None and (worker_id, attempt) != fence:
        return None

    row = session.execute(
        update(Submission)
        .where(Submission.id == submission_id, Submission.status == status)
        .values(status=to, updated_at=utcnow(), **(values or {}))
        .returning(Submission)
        .execution_options(synchronize_session=False, populate_existing=True)
    ).scalar_one()
    session.execute(
        insert(SubmissionTransition).values(
            submission_id=submission_id, from_status=status, to_status=to, attempt=row.attempt, actor=actor
        )
    )
    return row
