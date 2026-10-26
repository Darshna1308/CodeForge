import redis
from fastapi import APIRouter, Depends, Query
from sqlalchemy import Integer, case, distinct, func, select
from sqlalchemy.orm import Session

from codeforge_core import keys
from codeforge_core.enums import SubmissionMode, Verdict
from codeforge_core.models import Problem, Submission, User

from ..cache import get_or_load
from ..deps import get_current_user, get_db, get_r
from ..errors import APIError
from ..schemas import ProfileOut, SolvedByDifficulty, UserOut

router = APIRouter(prefix="/users", tags=["users"])


def _profile(db: Session, user: User) -> ProfileOut:
    judged = (Submission.user_id == user.id, Submission.mode == SubmissionMode.SUBMIT)
    total, accepted = db.execute(
        select(func.count(), func.coalesce(func.sum(case((Submission.verdict == Verdict.ACCEPTED, 1), else_=0)), 0))
        .where(*judged)
    ).one()
    by_diff = dict(db.execute(
        select(Problem.difficulty, func.count(distinct(Problem.id)))
        .join(Submission, Submission.problem_id == Problem.id)
        .where(*judged, Submission.verdict == Verdict.ACCEPTED)
        .group_by(Problem.difficulty)
    ).all())
    recent = db.execute(
        select(Problem.slug, Problem.title, func.max(Submission.finished_at).label("at"))
        .join(Submission, Submission.problem_id == Problem.id)
        .where(*judged, Submission.verdict == Verdict.ACCEPTED)
        .group_by(Problem.slug, Problem.title)
        .order_by(func.max(Submission.finished_at).desc())
        .limit(10)
    ).all()
    solved = SolvedByDifficulty(**{d.value: c for d, c in by_diff.items()})
    return ProfileOut(
        username=user.username, joined_at=user.created_at, solved=solved.EASY + solved.MEDIUM + solved.HARD,
        solved_by_difficulty=solved, submissions=int(total), accepted_submissions=int(accepted),
        recent_accepted=[{"slug": s, "title": t, "at": at} for s, t, at in recent],
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.get("/me/profile", response_model=ProfileOut)
def my_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _profile(db, user)


@router.get("/leaderboard")
def leaderboard(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db), r: redis.Redis = Depends(get_r)):
    """Top solvers by distinct problems accepted. Cache-aside, 30s TTL."""

    def load():
        rows = db.execute(
            select(
                User.username,
                func.count(distinct(Submission.problem_id)).label("solved"),
                func.count().label("accepted_submissions"),
                func.min(Submission.finished_at).label("first_ac"),
            )
            .join(Submission, Submission.user_id == User.id)
            .where(Submission.mode == SubmissionMode.SUBMIT, Submission.verdict == Verdict.ACCEPTED)
            .group_by(User.id)
            .order_by(func.count(distinct(Submission.problem_id)).desc(), func.min(Submission.finished_at))
            .limit(100)
        ).all()
        return [{"rank": i + 1, "username": u, "solved": s, "accepted_submissions": a} for i, (u, s, a, _) in enumerate(rows)]

    data, hit = get_or_load(r, "leaderboard", keys.cache_stats("leaderboard"), 30, load)
    return {"items": data[:limit], "cached": hit}


@router.get("/{username}", response_model=ProfileOut)
def public_profile(username: str, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(func.lower(User.username) == username.lower())).scalar_one_or_none()
    if user is None:
        raise APIError(404, "not_found", "User not found")
    return _profile(db, user)
