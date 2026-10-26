import threading

import pytest
from sqlalchemy import select

from codeforge_core.db import get_sessionmaker
from codeforge_core.enums import SubmissionMode, SubmissionStatus as S
from codeforge_core.models import Problem, Submission, SubmissionTransition, User
from codeforge_core.repository import transition
from codeforge_core.state_machine import IN_PROGRESS, TERMINAL, TRANSITIONS, InvalidTransition, assert_transition, can_transition


def test_terminal_states_have_no_exits():
    for s in TERMINAL:
        assert TRANSITIONS[s] == frozenset()


def test_every_state_can_reach_a_terminal_state():
    for start in S:
        seen, frontier = {start}, [start]
        while frontier:
            for nxt in TRANSITIONS[frontier.pop()]:
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append(nxt)
        assert seen & TERMINAL, start


@pytest.mark.parametrize("src,dst", [
    (S.CREATED, S.COMPLETED), (S.QUEUED, S.RUNNING), (S.COMPLETED, S.QUEUED),
    (S.CANCELLED, S.QUEUED), (S.RUNNING, S.CANCELLED), (S.JUDGING, S.COMPILING),
])
def test_illegal_transitions_rejected(src, dst):
    assert not can_transition(src, dst)
    with pytest.raises(InvalidTransition):
        assert_transition(src, dst)


def test_in_progress_states_can_be_requeued_for_crash_recovery():
    for s in IN_PROGRESS:
        assert can_transition(s, S.QUEUED)
        assert can_transition(s, S.INTERNAL_ERROR)


def _new_submission(status=S.QUEUED) -> int:
    Session = get_sessionmaker()
    with Session.begin() as s:
        user = s.execute(select(User).limit(1)).scalar_one_or_none()
        if user is None:
            user = User(username="sm_user", email="sm@example.com", password_hash="x")
            s.add(user)
            s.flush()
        problem = s.execute(select(Problem).limit(1)).scalar_one()
        sub = Submission(user_id=user.id, problem_id=problem.id, language="python", mode=SubmissionMode.SUBMIT,
                         source_code="print(1)", status=status)
        s.add(sub)
        s.flush()
        return sub.id


def test_transition_rejects_illegal_move_in_database():
    sid = _new_submission(S.QUEUED)
    with get_sessionmaker().begin() as s:
        assert transition(s, sid, S.COMPLETED, actor="test") is None
    with get_sessionmaker().begin() as s:
        assert s.get(Submission, sid).status == S.QUEUED


def test_concurrent_claims_exactly_one_wins():
    """20 threads race to claim the same QUEUED row; the row lock lets exactly one through."""
    sid = _new_submission(S.QUEUED)
    barrier = threading.Barrier(20)
    winners: list[str] = []
    lock = threading.Lock()

    def claim(i: int) -> None:
        barrier.wait()
        with get_sessionmaker().begin() as s:
            row = transition(s, sid, S.PROCESSING, actor=f"w{i}", expected_from={S.QUEUED},
                             values={"worker_id": f"w{i}", "attempt": Submission.attempt + 1})
            if row is not None:
                with lock:
                    winners.append(f"w{i}")

    threads = [threading.Thread(target=claim, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(winners) == 1
    with get_sessionmaker().begin() as s:
        sub = s.get(Submission, sid)
        assert sub.status == S.PROCESSING and sub.attempt == 1 and sub.worker_id == winners[0]
        audit = s.execute(select(SubmissionTransition).where(SubmissionTransition.submission_id == sid)).scalars().all()
        assert [(a.from_status, a.to_status) for a in audit] == [(S.QUEUED, S.PROCESSING)]


def test_fencing_token_blocks_stale_worker():
    sid = _new_submission(S.QUEUED)
    Session = get_sessionmaker()
    with Session.begin() as s:
        transition(s, sid, S.PROCESSING, actor="old", values={"worker_id": "old", "attempt": 1})
    # Sweeper decides "old" is dead and re-queues; a new worker claims attempt 2.
    with Session.begin() as s:
        assert transition(s, sid, S.QUEUED, actor="sweeper", fence=("old", 1)) is not None
    with Session.begin() as s:
        assert transition(s, sid, S.PROCESSING, actor="new", values={"worker_id": "new", "attempt": 2}) is not None
    # The old worker wakes up and tries to keep going: rejected by the fence.
    with Session.begin() as s:
        assert transition(s, sid, S.RUNNING, actor="old", fence=("old", 1)) is None
    with Session.begin() as s:
        assert transition(s, sid, S.RUNNING, actor="new", fence=("new", 2)) is not None
