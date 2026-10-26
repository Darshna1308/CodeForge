import hashlib

import redis
from fastapi import APIRouter, Depends, Query
from sqlalchemy import Integer, and_, case, func, or_, select
from sqlalchemy.orm import Session

from codeforge_core import keys
from codeforge_core.config import get_settings
from codeforge_core.enums import Difficulty, SubmissionMode, Verdict
from codeforge_core.languages import LANGUAGES
from codeforge_core.models import Problem, ProblemTag, Submission, Tag, TestCase, User

from ..cache import generation, get_or_load, invalidate_problems
from ..deps import get_db, get_optional_user, get_r, require_admin
from ..errors import APIError
from ..schemas import LanguageOut, Page, ProblemDetail, ProblemSummary, TagOut

router = APIRouter(prefix="/problems", tags=["problems"])


def _acceptance_subquery():
    """Per-problem judged submission counts (RUN mode excluded)."""
    return (
        select(
            Submission.problem_id.label("pid"),
            func.count().label("total"),
            func.sum(case((Submission.verdict == Verdict.ACCEPTED, 1), else_=0)).cast(Integer).label("accepted"),
        )
        .where(Submission.mode == SubmissionMode.SUBMIT, Submission.verdict.is_not(None))
        .group_by(Submission.problem_id)
        .subquery()
    )


def _rate(accepted: int, total: int) -> float | None:
    return round(accepted * 100.0 / total, 1) if total else None


def _user_status(db: Session, user: User | None, problem_ids: list[int]) -> dict[int, str]:
    if user is None or not problem_ids:
        return {}
    rows = db.execute(
        select(
            Submission.problem_id,
            func.bool_or(Submission.verdict == Verdict.ACCEPTED),
        )
        .where(Submission.user_id == user.id, Submission.mode == SubmissionMode.SUBMIT, Submission.problem_id.in_(problem_ids))
        .group_by(Submission.problem_id)
    ).all()
    return {pid: ("solved" if solved else "attempted") for pid, solved in rows}


def _load_list(db: Session, search: str | None, difficulty: Difficulty | None, tag: str | None) -> list[dict]:
    acc = _acceptance_subquery()
    q = (
        select(Problem, func.coalesce(acc.c.accepted, 0), func.coalesce(acc.c.total, 0))
        .outerjoin(acc, acc.c.pid == Problem.id)
        .where(Problem.is_published.is_(True))
        .order_by(Problem.id)
    )
    if search:
        like = f"%{search.lower()}%"
        q = q.where(or_(func.lower(Problem.title).like(like), Problem.slug.like(like)))
    if difficulty:
        q = q.where(Problem.difficulty == difficulty)
    if tag:
        q = q.where(Problem.id.in_(select(ProblemTag.problem_id).join(Tag, Tag.id == ProblemTag.tag_id).where(Tag.slug == tag)))
    out = []
    for p, accepted, total in db.execute(q).all():
        out.append({
            "id": p.id, "slug": p.slug, "title": p.title, "difficulty": p.difficulty.value,
            "tags": [{"slug": t.slug, "name": t.name} for t in p.tags],
            "accepted": accepted, "submissions": total, "acceptance_rate": _rate(accepted, total),
        })
    return out


@router.get("", response_model=Page[ProblemSummary])
def list_problems(
    search: str | None = Query(default=None, max_length=80),
    difficulty: Difficulty | None = None,
    tag: str | None = Query(default=None, max_length=48),
    status: str | None = Query(default=None, pattern="^(solved|attempted|todo)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_r),
    user: User | None = Depends(get_optional_user),
):
    s = get_settings()
    fingerprint = hashlib.sha1(f"{search or ''}|{difficulty or ''}|{tag or ''}".encode()).hexdigest()[:16]
    rows, _ = get_or_load(
        r, "problem_list", keys.cache_problem_list(generation(r), fingerprint), s.cache_ttl_problem_list,
        lambda: _load_list(db, search, difficulty, tag),
    )
    # Per-user status is personal data: merged after the shared cache lookup, never cached.
    statuses = _user_status(db, user, [row["id"] for row in rows])
    items = [ProblemSummary(**row, status=statuses.get(row["id"])) for row in rows]
    if status:
        items = [i for i in items if (i.status or "todo") == status]
    total = len(items)
    start = (page - 1) * page_size
    return Page(items=items[start:start + page_size], total=total, page=page, page_size=page_size)


@router.get("/tags", response_model=list[TagOut])
def list_tags(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Tag.slug, Tag.name, func.count(ProblemTag.problem_id))
        .join(ProblemTag, ProblemTag.tag_id == Tag.id)
        .group_by(Tag.id)
        .order_by(Tag.name)
    ).all()
    return [TagOut(slug=s, name=n, count=c) for s, n, c in rows]


def _load_detail(db: Session, slug: str) -> dict | None:
    p = db.execute(select(Problem).where(Problem.slug == slug, Problem.is_published.is_(True))).scalar_one_or_none()
    if p is None:
        return None
    # Only sample tests are selected; hidden tests never leave the database on this path.
    samples = db.execute(
        select(TestCase).where(TestCase.problem_id == p.id, TestCase.is_sample.is_(True)).order_by(TestCase.ordinal)
    ).scalars().all()
    hidden = db.execute(
        select(func.count()).select_from(TestCase).where(TestCase.problem_id == p.id, TestCase.is_sample.is_(False))
    ).scalar_one()
    acc = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(case((Submission.verdict == Verdict.ACCEPTED, 1), else_=0)), 0),
        ).where(and_(Submission.problem_id == p.id, Submission.mode == SubmissionMode.SUBMIT, Submission.verdict.is_not(None)))
    ).one()
    total, accepted = int(acc[0]), int(acc[1])
    return {
        "id": p.id, "slug": p.slug, "title": p.title, "difficulty": p.difficulty.value,
        "statement": p.statement, "input_spec": p.input_spec, "output_spec": p.output_spec,
        "constraints": p.constraints, "time_limit_ms": p.time_limit_ms, "memory_limit_mb": p.memory_limit_mb,
        "tags": [{"slug": t.slug, "name": t.name} for t in p.tags],
        "examples": [{"input": t.input, "output": t.expected_output, "explanation": t.explanation} for t in samples],
        "hidden_test_count": hidden,
        "accepted": accepted, "submissions": total, "acceptance_rate": _rate(accepted, total),
        "languages": [
            LanguageOut(key=l.key, display_name=l.display_name, version=l.version,
                        monaco_language=l.monaco_language, template=l.template).model_dump()
            for l in LANGUAGES.values()
        ],
    }


@router.get("/{slug}", response_model=ProblemDetail)
def get_problem(
    slug: str, db: Session = Depends(get_db), r: redis.Redis = Depends(get_r), user: User | None = Depends(get_optional_user)
):
    data, _ = get_or_load(r, "problem_detail", keys.cache_problem(generation(r), slug), get_settings().cache_ttl_problem,
                          lambda: _load_detail(db, slug))
    if data is None:
        raise APIError(404, "not_found", f"Problem '{slug}' not found")
    status = _user_status(db, user, [data["id"]]).get(data["id"])
    return ProblemDetail(**data, status=status)


@router.post("/cache/invalidate", tags=["admin"])
def invalidate_cache(_: User = Depends(require_admin), r: redis.Redis = Depends(get_r)):
    """Bump the cache generation, orphaning every cached problem list/detail entry."""
    return {"generation": invalidate_problems(r)}
