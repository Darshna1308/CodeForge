"""Reliable job queue on Redis Streams.

Semantics (see docs/QUEUE_AND_CONCURRENCY.md):

* XADD appends a job; consumer groups give each message to exactly one
  consumer at a time, and the message stays in the group's Pending Entries
  List (PEL) until XACK. That makes delivery *at-least-once*: a consumer that
  crashes before XACK leaves the message pending, and another consumer later
  takes it over with XAUTOCLAIM once it has been idle for the visibility
  timeout.
* At-least-once delivery means duplicates are normal. Exactly-once *effects*
  come from the database, not from Redis: the claim is a compare-and-set on
  the submission row (status must be QUEUED), so a duplicate delivery simply
  fails the CAS and is acknowledged without doing work.
* The stream is a delivery mechanism, not the source of truth. If Redis loses
  a message, the sweeper notices a stale QUEUED/CREATED row and re-enqueues.
"""

import time
from dataclasses import dataclass

import redis

from . import keys
from .enums import SubmissionMode

MAXLEN = 100_000


@dataclass(frozen=True)
class Job:
    stream: str
    message_id: str
    submission_id: int
    enqueued_at_ms: int
    deliveries: int = 1


def stream_for(mode: SubmissionMode) -> str:
    return keys.STREAM_RUN if mode == SubmissionMode.RUN else keys.STREAM_SUBMIT


def ensure_groups(r: redis.Redis) -> None:
    for stream in (keys.STREAM_RUN, keys.STREAM_SUBMIT):
        try:
            r.xgroup_create(stream, keys.CONSUMER_GROUP, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise


def enqueue(r: redis.Redis, submission_id: int, mode: SubmissionMode) -> str:
    return r.xadd(
        stream_for(mode),
        {"submission_id": str(submission_id), "enqueued_at_ms": str(int(time.time() * 1000))},
        maxlen=MAXLEN,
        approximate=True,
    )


def _to_jobs(stream: str, entries) -> list[Job]:
    jobs = []
    for message_id, fields in entries:
        if not fields:  # entry was trimmed/deleted while pending
            continue
        jobs.append(
            Job(
                stream=stream,
                message_id=message_id,
                submission_id=int(fields["submission_id"]),
                enqueued_at_ms=int(fields.get("enqueued_at_ms", 0)),
            )
        )
    return jobs


def read_many(r: redis.Redis, consumer: str, streams: list[str], block_ms: int | None) -> list[Job]:
    """XREADGROUP with COUNT 1 *per stream*: may return one job from each stream.

    Every returned job is now in this consumer's PEL and must be processed or
    it will only come back via XAUTOCLAIM after the visibility timeout.
    """
    resp = r.xreadgroup(keys.CONSUMER_GROUP, consumer, {s: ">" for s in streams}, count=1, block=block_ms)
    jobs: list[Job] = []
    for stream, entries in resp or []:
        jobs.extend(_to_jobs(stream, entries))
    return jobs


def read(r: redis.Redis, consumer: str, streams: list[str], block_ms: int | None) -> Job | None:
    """Single-stream convenience wrapper around :func:`read_many`."""
    assert len(streams) == 1, "use read_many for multi-stream reads"
    jobs = read_many(r, consumer, streams, block_ms)
    return jobs[0] if jobs else None


def ack(r: redis.Redis, job: Job) -> None:
    r.xack(job.stream, keys.CONSUMER_GROUP, job.message_id)


def autoclaim(r: redis.Redis, consumer: str, stream: str, min_idle_ms: int, count: int = 10) -> list[Job]:
    """Take over messages whose consumer stopped acknowledging (crashed or hung)."""
    resp = r.xautoclaim(stream, keys.CONSUMER_GROUP, consumer, min_idle_time=min_idle_ms, start_id="0-0", count=count)
    entries = resp[1] if resp else []
    jobs = _to_jobs(stream, entries)
    if not jobs:
        return []
    # Attach delivery counts so poison messages can be dead-lettered.
    pending = r.xpending_range(stream, keys.CONSUMER_GROUP, min=jobs[0].message_id, max=jobs[-1].message_id, count=len(jobs) + 10)
    counts = {p["message_id"]: p["times_delivered"] for p in pending}
    return [Job(j.stream, j.message_id, j.submission_id, j.enqueued_at_ms, counts.get(j.message_id, 1)) for j in jobs]


def dead_letter(r: redis.Redis, job: Job, reason: str) -> None:
    pipe = r.pipeline()
    pipe.xadd(
        keys.STREAM_DEAD,
        {"submission_id": str(job.submission_id), "source": job.stream, "message_id": job.message_id, "reason": reason},
        maxlen=10_000,
        approximate=True,
    )
    pipe.xack(job.stream, keys.CONSUMER_GROUP, job.message_id)
    pipe.execute()


def depth(r: redis.Redis) -> dict[str, dict[str, int]]:
    """Backlog (undelivered) and in-flight (pending, unacked) per stream."""
    out: dict[str, dict[str, int]] = {}
    for name, stream in (("run", keys.STREAM_RUN), ("submit", keys.STREAM_SUBMIT)):
        backlog = pending = 0
        try:
            for g in r.xinfo_groups(stream):
                if g["name"] == keys.CONSUMER_GROUP:
                    pending = int(g.get("pending", 0) or 0)
                    lag = g.get("lag")
                    backlog = int(lag) if lag is not None else 0
        except redis.ResponseError:
            pass
        out[name] = {"backlog": backlog, "in_flight": pending}
    try:
        out["dead"] = {"total": int(r.xlen(keys.STREAM_DEAD))}
    except redis.ResponseError:
        out["dead"] = {"total": 0}
    return out
