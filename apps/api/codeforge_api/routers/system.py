"""Health, readiness, Prometheus metrics and dashboard statistics.

Everything reported here is measured: queue depth comes from XINFO GROUPS,
active workers from live heartbeat keys, latencies and verdict counts from
Postgres. Nothing is synthesised.
"""

import time
from datetime import timedelta

import redis
from fastapi import APIRouter, Depends, Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from prometheus_client.core import GaugeMetricFamily
from sqlalchemy import Integer, case, func, select, text
from sqlalchemy.orm import Session

from codeforge_core import keys
from codeforge_core import queue as cfqueue
from codeforge_core.config import get_settings
from codeforge_core.db import get_engine
from codeforge_core.enums import AttemptOutcome, SubmissionMode, SubmissionStatus as S, Verdict
from codeforge_core.languages import LANGUAGES
from codeforge_core.models import ExecutionAttempt, Problem, Submission, User
from codeforge_core.redis_client import get_redis
from codeforge_core.repository import utcnow
from codeforge_core.state_machine import IN_PROGRESS

from ..cache import get_or_load
from ..deps import get_db, get_r

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    """Liveness: the process is up and serving. No dependency checks."""
    return {"status": "ok"}


@router.get("/ready")
def ready(response: Response):
    """Readiness: can this instance do useful work (Postgres + Redis reachable)?"""
    checks: dict[str, dict] = {}
    t = time.perf_counter()
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["postgres"] = {"ok": True, "latency_ms": round((time.perf_counter() - t) * 1000, 2)}
    except Exception as exc:
        checks["postgres"] = {"ok": False, "error": type(exc).__name__}
    t = time.perf_counter()
    try:
        get_redis().ping()
        checks["redis"] = {"ok": True, "latency_ms": round((time.perf_counter() - t) * 1000, 2)}
    except Exception as exc:
        checks["redis"] = {"ok": False, "error": type(exc).__name__}
    ok = all(c["ok"] for c in checks.values())
    response.status_code = 200 if ok else 503
    return {"status": "ready" if ok else "degraded", "checks": checks}


def active_workers(r: redis.Redis) -> list[dict]:
    workers = []
    for key in r.scan_iter(match=f"{keys.WORKER_PREFIX}*", count=100):
        h = r.hgetall(key)
        if h:
            workers.append({
                "worker_id": h.get("worker_id"), "host": h.get("host"),
                "concurrency": int(h.get("concurrency", 0)), "busy": int(h.get("busy", 0)),
                "handled": int(h.get("handled", 0)), "started_at": int(h.get("started_at", 0)),
                "last_seen": int(h.get("last_seen", 0)),
            })
    return sorted(workers, key=lambda w: w["worker_id"] or "")


class QueueCollector:
    """Scrape-time gauges read straight from Redis (no background polling)."""

    def collect(self):
        r = get_redis()
        depth = GaugeMetricFamily("codeforge_queue_backlog", "Messages not yet delivered", labels=["stream"])
        inflight = GaugeMetricFamily("codeforge_queue_in_flight", "Delivered but unacknowledged messages", labels=["stream"])
        workers = GaugeMetricFamily("codeforge_active_workers", "Workers with a live heartbeat")
        try:
            d = cfqueue.depth(r)
            for name in ("run", "submit"):
                depth.add_metric([name], d[name]["backlog"])
                inflight.add_metric([name], d[name]["in_flight"])
            workers.add_metric([], len(active_workers(r)))
        except redis.RedisError:
            return
        yield depth
        yield inflight
        yield workers


_collector_registered = False


def register_collectors() -> None:
    global _collector_registered
    if not _collector_registered:
        REGISTRY.register(QueueCollector())
        _collector_registered = True


@router.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


@router.get("/stats/overview", tags=["stats"])
def overview(db: Session = Depends(get_db), r: redis.Redis = Depends(get_r)):
    """Landing-page numbers (cache-aside, short TTL)."""

    def load():
        judged = Submission.mode == SubmissionMode.SUBMIT
        total, accepted = db.execute(
            select(func.count(), func.coalesce(func.sum(case((Submission.verdict == Verdict.ACCEPTED, 1), else_=0)), 0)).where(judged)
        ).one()
        executions = db.execute(select(func.count()).select_from(Submission)).scalar_one()
        p50 = db.execute(
            select(func.percentile_cont(0.5).within_group(Submission.runtime_ms)).where(Submission.runtime_ms.is_not(None))
        ).scalar_one()
        return {
            "problems": db.execute(select(func.count()).select_from(Problem)).scalar_one(),
            "users": db.execute(select(func.count()).select_from(User)).scalar_one(),
            "submissions": int(total),
            "executions": int(executions),
            "accepted": int(accepted),
            "acceptance_rate": round(int(accepted) * 100 / int(total), 1) if total else None,
            "median_runtime_ms": round(float(p50), 1) if p50 is not None else None,
            "languages": [l.display_name for l in LANGUAGES.values()],
        }

    data, hit = get_or_load(r, "stats_overview", keys.cache_stats("overview"), get_settings().cache_ttl_stats, load)
    try:
        data["active_workers"] = len(active_workers(r))
    except redis.RedisError:
        data["active_workers"] = None
    return data


@router.get("/stats/system", tags=["stats"])
def system_stats(db: Session = Depends(get_db), r: redis.Redis = Depends(get_r)):
    """Dashboard: live queue/worker state from Redis + aggregates from Postgres."""
    live: dict = {"available": True}
    try:
        live["queue"] = cfqueue.depth(r)
        live["workers"] = active_workers(r)
        live["counters"] = {
            "jobs_completed": int(r.get(keys.COUNTER_JOBS_COMPLETED) or 0),
            "jobs_failed": int(r.get(keys.COUNTER_JOBS_FAILED) or 0),
            "duplicate_deliveries": int(r.get(keys.COUNTER_DUPLICATES) or 0),
            "redelivered": int(r.get(keys.COUNTER_REDELIVERED) or 0),
        }
    except redis.RedisError:
        live = {"available": False}

    def load():
        now = utcnow()
        since = now - timedelta(hours=24)
        by_status = dict(db.execute(select(Submission.status, func.count()).group_by(Submission.status)).all())
        verdicts = dict(db.execute(
            select(Submission.verdict, func.count()).where(Submission.verdict.is_not(None)).group_by(Submission.verdict)
        ).all())
        lat = db.execute(
            select(
                func.avg(ExecutionAttempt.total_ms), func.avg(ExecutionAttempt.queue_wait_ms),
                func.avg(ExecutionAttempt.sandbox_start_ms), func.avg(ExecutionAttempt.compile_ms),
                func.percentile_cont(0.95).within_group(ExecutionAttempt.total_ms),
                func.count(),
            ).where(ExecutionAttempt.started_at >= since, ExecutionAttempt.outcome == AttemptOutcome.SUCCEEDED)
        ).one()
        attempts = dict(db.execute(
            select(ExecutionAttempt.outcome, func.count()).group_by(ExecutionAttempt.outcome)
        ).all())
        series = db.execute(text("""
            SELECT b.bucket,
                   COUNT(s.id) AS total,
                   COUNT(s.id) FILTER (WHERE s.verdict = 'ACCEPTED') AS accepted
            FROM generate_series(date_trunc('hour', now()) - interval '23 hours', date_trunc('hour', now()), interval '1 hour') AS b(bucket)
            LEFT JOIN submissions s ON date_trunc('hour', s.created_at) = b.bucket
            GROUP BY b.bucket ORDER BY b.bucket
        """)).all()
        recent = db.execute(
            select(ExecutionAttempt.submission_id, ExecutionAttempt.attempt_no, ExecutionAttempt.worker_id,
                   ExecutionAttempt.outcome, ExecutionAttempt.total_ms, ExecutionAttempt.queue_wait_ms,
                   ExecutionAttempt.started_at, Submission.verdict, Submission.language)
            .join(Submission, Submission.id == ExecutionAttempt.submission_id)
            .order_by(ExecutionAttempt.id.desc()).limit(15)
        ).all()

        def f(v):
            return round(float(v), 1) if v is not None else None

        return {
            "status_counts": {k.value: v for k, v in by_status.items()},
            "in_progress": sum(v for k, v in by_status.items() if k in IN_PROGRESS),
            "verdicts": {k.value: v for k, v in verdicts.items()},
            "attempt_outcomes": {k.value: v for k, v in attempts.items()},
            "latency_24h": {
                "jobs": lat[5], "avg_total_ms": f(lat[0]), "avg_queue_wait_ms": f(lat[1]),
                "avg_sandbox_start_ms": f(lat[2]), "avg_compile_ms": f(lat[3]), "p95_total_ms": f(lat[4]),
            },
            "submissions_per_hour": [{"hour": b.isoformat(), "total": t, "accepted": a} for b, t, a in series],
            "recent_jobs": [
                {"submission_id": sid, "display_id": f"CF-{sid}", "attempt": an, "worker_id": w, "outcome": o.value,
                 "total_ms": tm, "queue_wait_ms": qw, "started_at": st, "verdict": v.value if v else None, "language": lang}
                for sid, an, w, o, tm, qw, st, v, lang in recent
            ],
        }

    data, _ = get_or_load(r, "stats_system", keys.cache_stats("system"), 3, load)
    return {"live": live, "db": data, "generated_at": utcnow()}
