import time

from codeforge_core import keys
from codeforge_core import queue as cfqueue
from codeforge_core.enums import SubmissionMode
from codeforge_core.redis_client import get_redis


def _fresh():
    r = get_redis()
    r.delete(keys.STREAM_RUN, keys.STREAM_SUBMIT, keys.STREAM_DEAD)
    cfqueue.ensure_groups(r)
    return r


def test_each_message_goes_to_one_consumer():
    r = _fresh()
    for i in range(6):
        cfqueue.enqueue(r, 1000 + i, SubmissionMode.SUBMIT)
    got = {"a": [], "b": []}
    for _ in range(3):
        for c in ("a", "b"):
            job = cfqueue.read(r, c, [keys.STREAM_SUBMIT], block_ms=None)
            got[c].append(job.submission_id)
    assert sorted(got["a"] + got["b"]) == list(range(1000, 1006))
    assert not set(got["a"]) & set(got["b"])


def test_unacked_message_is_reclaimed_after_visibility_timeout():
    r = _fresh()
    cfqueue.enqueue(r, 42, SubmissionMode.RUN)
    job = cfqueue.read(r, "crashed-consumer", [keys.STREAM_RUN], block_ms=None)
    assert job.submission_id == 42
    assert cfqueue.autoclaim(r, "rescuer", keys.STREAM_RUN, min_idle_ms=10_000) == []  # not idle long enough
    time.sleep(0.15)
    reclaimed = cfqueue.autoclaim(r, "rescuer", keys.STREAM_RUN, min_idle_ms=100)
    assert [j.submission_id for j in reclaimed] == [42]
    assert reclaimed[0].deliveries == 2
    cfqueue.ack(r, reclaimed[0])
    assert cfqueue.depth(r)["run"]["in_flight"] == 0


def test_multi_stream_read_returns_every_delivered_message():
    r = _fresh()
    cfqueue.enqueue(r, 1, SubmissionMode.RUN)
    cfqueue.enqueue(r, 2, SubmissionMode.SUBMIT)
    jobs = cfqueue.read_many(r, "c", [keys.STREAM_SUBMIT, keys.STREAM_RUN], block_ms=None)
    assert sorted(j.submission_id for j in jobs) == [1, 2]


def test_dead_letter_acks_and_records():
    r = _fresh()
    cfqueue.enqueue(r, 7, SubmissionMode.SUBMIT)
    job = cfqueue.read(r, "c", [keys.STREAM_SUBMIT], block_ms=None)
    cfqueue.dead_letter(r, job, "test")
    d = cfqueue.depth(r)
    assert d["submit"]["in_flight"] == 0 and d["dead"]["total"] == 1
