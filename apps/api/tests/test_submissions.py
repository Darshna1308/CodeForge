import concurrent.futures as cf
import uuid

from fastapi.testclient import TestClient

from codeforge_api.main import app
from codeforge_core import keys
from codeforge_core.redis_client import get_redis

from api_helpers import register

SRC = "print(1)\n"


def body(**kw):
    return {"problem_slug": "two-sum", "language": "python", "source_code": SRC, **kw}


def test_requires_auth(client):
    client.cookies.clear()
    r = client.post("/submissions", json=body())
    assert r.status_code == 401


def test_create_persists_and_enqueues(client, auth):
    r = get_redis()
    before = r.xlen(keys.STREAM_SUBMIT)
    res = client.post("/submissions", json=body(), headers=auth)
    assert res.status_code == 202
    data = res.json()
    assert data["status"] == "QUEUED" and data["display_id"] == f"CF-{data['id']}"
    assert r.xlen(keys.STREAM_SUBMIT) == before + 1
    detail = client.get(f"/submissions/{data['id']}", headers=auth).json()
    assert [t["to_status"] for t in detail["transitions"]] == ["CREATED", "QUEUED"]


def test_run_mode_goes_to_priority_stream(client, auth):
    r = get_redis()
    before = r.xlen(keys.STREAM_RUN)
    res = client.post("/executions", json=body(custom_input="1 2\n"), headers=auth)
    assert res.status_code == 202 and res.json()["mode"] == "RUN"
    assert r.xlen(keys.STREAM_RUN) == before + 1


def test_validation_errors(client, auth):
    assert client.post("/submissions", json=body(language="brainfuck"), headers=auth).status_code == 422
    assert client.post("/submissions", json=body(problem_slug="nope"), headers=auth).status_code == 404
    assert client.post("/submissions", json=body(source_code="   "), headers=auth).status_code == 422
    big = client.post("/executions", json=body(source_code="#" * 70_000), headers=auth)
    assert big.status_code == 413
    assert client.post("/executions", json=body(custom_input="x" * 70_000), headers=auth).status_code == 413
    assert client.post("/submissions", json=body(), headers={**auth, "Idempotency-Key": "bad key!"}).status_code == 422


def test_other_users_get_404(client, auth):
    sid = client.post("/executions", json=body(), headers=auth).json()["id"]
    _, other = register(client)
    assert client.get(f"/submissions/{sid}", headers=other).status_code == 404
    assert client.get(f"/submissions/{sid}/events", headers=other).status_code == 404
    assert client.post(f"/submissions/{sid}/cancel", headers=other).status_code == 404


def test_cancel_queued_then_cannot_cancel_again(client, auth):
    sid = client.post("/executions", json=body(), headers=auth).json()["id"]
    r = client.post(f"/submissions/{sid}/cancel", headers=auth)
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    assert client.post(f"/submissions/{sid}/cancel", headers=auth).status_code == 409


def test_idempotency_key_concurrent_posts_create_one_submission(client):
    _, headers = register(client)
    key = f"k-{uuid.uuid4().hex}"
    stream_before = get_redis().xlen(keys.STREAM_RUN)

    def post(_):
        with TestClient(app) as c:
            return c.post("/executions", json=body(), headers={**headers, "Idempotency-Key": key})

    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(post, range(8)))
    assert all(r.status_code in (200, 202) for r in responses), [r.text for r in responses]
    ids = {r.json()["id"] for r in responses}
    assert len(ids) == 1
    assert sum(r.status_code == 202 for r in responses) == 1
    assert get_redis().xlen(keys.STREAM_RUN) == stream_before + 1  # enqueued exactly once


def test_submit_rate_limit_returns_429_with_retry_after(client):
    _, headers = register(client)  # RATE_LIMIT_SUBMIT=5/60 in tests
    codes = [client.post("/submissions", json=body(), headers=headers).status_code for _ in range(7)]
    assert codes[:5] == [202] * 5 and codes[5:] == [429, 429]
    r = client.post("/submissions", json=body(), headers=headers)
    assert int(r.headers["Retry-After"]) >= 1 and r.json()["error"]["code"] == "rate_limited"


def test_history_is_paginated_and_private(client):
    _, headers = register(client)
    for _ in range(3):
        client.post("/submissions", json=body(), headers=headers)
    page = client.get("/submissions?page_size=2", headers=headers).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    _, other = register(client)
    assert client.get("/submissions", headers=other).json()["total"] == 0


def test_redis_outage_keeps_submission_in_outbox(client, monkeypatch):
    """If XADD fails after commit, the API still returns 202 and the row waits (CREATED) for the sweeper."""
    import codeforge_core.queue as q
    import redis

    _, headers = register(client)

    def boom(*a, **k):
        raise redis.ConnectionError("simulated outage")

    monkeypatch.setattr(q, "enqueue", boom)
    res = client.post("/executions", json=body(), headers=headers)
    assert res.status_code == 202 and res.json()["status"] == "CREATED"
