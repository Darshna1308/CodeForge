"""Idempotent seeding: ``python -m codeforge_api.seed``.

Upserts problems by slug and replaces their tests, so re-running after editing
a generator is safe. Bumps the cache generation afterwards so no stale problem
data is served. Optionally creates an admin user when CODEFORGE_ADMIN_PASSWORD
is set (no credentials live in source).
"""

import logging
import os
import random
import sys

import redis
from sqlalchemy import delete, select

from codeforge_core import logging as cflog
from codeforge_core.config import get_settings
from codeforge_core.db import session_scope
from codeforge_core.enums import Difficulty, UserRole
from codeforge_core.models import Problem, ProblemTag, Tag, TestCase, User
from codeforge_core.redis_client import get_redis

from ..cache import invalidate_problems
from ..security import hash_password
from .problems import PROBLEMS

log = logging.getLogger("codeforge_api.seed")
SEED = 20261026


def seed(database_url: str | None = None) -> dict:
    counts = {"problems": 0, "tests": 0}
    with session_scope(database_url) as s:
        for idx, d in enumerate(PROBLEMS):
            rng = random.Random(SEED + idx)
            p = s.execute(select(Problem).where(Problem.slug == d.slug)).scalar_one_or_none()
            if p is None:
                p = Problem(slug=d.slug)
                s.add(p)
            p.title, p.difficulty = d.title, Difficulty(d.difficulty)
            p.statement, p.input_spec, p.output_spec, p.constraints = d.statement, d.input_spec, d.output_spec, d.constraints
            p.time_limit_ms, p.memory_limit_mb, p.is_published = d.time_limit_ms, d.memory_limit_mb, True
            s.flush()

            s.execute(delete(ProblemTag).where(ProblemTag.problem_id == p.id))
            for slug in d.tags:
                tag = s.execute(select(Tag).where(Tag.slug == slug)).scalar_one_or_none()
                if tag is None:
                    tag = Tag(slug=slug, name=slug.replace("-", " ").title())
                    s.add(tag)
                    s.flush()
                s.add(ProblemTag(problem_id=p.id, tag_id=tag.id))

            # Tests are replaced wholesale; submission_results keep their rows (FK -> SET NULL).
            s.execute(delete(TestCase).where(TestCase.problem_id == p.id))
            ordinal = 0
            for sample in d.samples:
                ordinal += 1
                s.add(TestCase(problem_id=p.id, ordinal=ordinal, is_sample=True, input=sample.input,
                               expected_output=d.solve(sample.input), explanation=sample.explanation))
            for hidden_input in d.hidden(rng):
                ordinal += 1
                s.add(TestCase(problem_id=p.id, ordinal=ordinal, is_sample=False, input=hidden_input,
                               expected_output=d.solve(hidden_input)))
            counts["problems"] += 1
            counts["tests"] += ordinal

        admin_password = os.environ.get("CODEFORGE_ADMIN_PASSWORD")
        if admin_password:
            admin = s.execute(select(User).where(User.username == "admin")).scalar_one_or_none()
            if admin is None:
                s.add(User(username="admin", email="admin@codeforge.local", password_hash=hash_password(admin_password), role=UserRole.ADMIN))
                counts["admin_created"] = 1
    try:
        invalidate_problems(get_redis())
    except redis.RedisError:
        log.warning("could not bump cache generation (redis unavailable)")
    return counts


if __name__ == "__main__":
    cflog.configure_logging("seed", get_settings().log_level)
    result = seed()
    log.info("seed complete", extra=result)
    sys.exit(0)
