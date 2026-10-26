"""Submission lifecycle state machine.

The table below is the single source of truth for legal transitions. Every
status change in the system goes through :func:`transition` (core.repository),
which turns the table into a compare-and-set ``UPDATE ... WHERE status IN (...)``
so that concurrent actors (API, several workers, the sweeper) can never apply
an illegal or stale transition, even without holding application-level locks.

    CREATED ─► QUEUED ─► PROCESSING ─┬─► COMPILING ─┬─► RUNNING ─► JUDGING ─► COMPLETED
                  ▲                  └──────────────┼─► RUNNING          (verdict set)
                  │                                 └─► COMPLETED  (compilation error)
                  └──── lease expired (sweeper) ◄── any in-progress state

    Any non-terminal state ─► INTERNAL_ERROR (attempts exhausted / unrecoverable)
    CREATED | QUEUED       ─► CANCELLED      (user cancelled before a worker claimed it)
"""

from collections.abc import Iterable

from .enums import SubmissionStatus as S

TERMINAL: frozenset[S] = frozenset({S.COMPLETED, S.INTERNAL_ERROR, S.CANCELLED})
IN_PROGRESS: frozenset[S] = frozenset({S.PROCESSING, S.COMPILING, S.RUNNING, S.JUDGING})

TRANSITIONS: dict[S, frozenset[S]] = {
    S.CREATED: frozenset({S.QUEUED, S.CANCELLED, S.INTERNAL_ERROR}),
    S.QUEUED: frozenset({S.PROCESSING, S.CANCELLED, S.INTERNAL_ERROR}),
    S.PROCESSING: frozenset({S.COMPILING, S.RUNNING, S.QUEUED, S.INTERNAL_ERROR}),
    S.COMPILING: frozenset({S.RUNNING, S.COMPLETED, S.QUEUED, S.INTERNAL_ERROR}),
    S.RUNNING: frozenset({S.JUDGING, S.QUEUED, S.INTERNAL_ERROR}),
    S.JUDGING: frozenset({S.COMPLETED, S.QUEUED, S.INTERNAL_ERROR}),
    S.COMPLETED: frozenset(),
    S.INTERNAL_ERROR: frozenset(),
    S.CANCELLED: frozenset(),
}


class InvalidTransition(Exception):
    def __init__(self, src: S, dst: S):
        super().__init__(f"illegal submission transition {src.value} -> {dst.value}")
        self.src = src
        self.dst = dst


def can_transition(src: S, dst: S) -> bool:
    return dst in TRANSITIONS[src]


def assert_transition(src: S, dst: S) -> None:
    if not can_transition(src, dst):
        raise InvalidTransition(src, dst)


def sources_for(dst: S, restrict_to: Iterable[S] | None = None) -> frozenset[S]:
    """All states from which ``dst`` is reachable in one step (optionally narrowed)."""
    srcs = frozenset(s for s, targets in TRANSITIONS.items() if dst in targets)
    if restrict_to is not None:
        srcs = srcs & frozenset(restrict_to)
    return srcs


def is_terminal(status: S) -> bool:
    return status in TERMINAL
