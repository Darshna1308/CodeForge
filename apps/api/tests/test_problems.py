from sqlalchemy import select

from codeforge_core import keys
from codeforge_core.db import get_sessionmaker
from codeforge_core.models import Problem, TestCase
from codeforge_core.redis_client import get_redis


def test_list_and_filters(client):
    items = client.get("/problems").json()["items"]
    assert len(items) == 10
    assert {p["difficulty"] for p in client.get("/problems?difficulty=HARD").json()["items"]} == {"HARD"}
    tagged = client.get("/problems?tag=dynamic-programming").json()["items"]
    assert {p["slug"] for p in tagged} == {"maximum-subarray", "coin-change"}
    assert [p["slug"] for p in client.get("/problems?search=island").json()["items"]] == ["number-of-islands"]
    assert client.get("/problems?page_size=500").status_code == 422


def test_detail_never_exposes_hidden_tests(client):
    r = client.get("/problems/two-sum")
    body = r.json()
    with get_sessionmaker()() as s:
        pid = s.execute(select(Problem.id).where(Problem.slug == "two-sum")).scalar_one()
        hidden = s.execute(select(TestCase).where(TestCase.problem_id == pid, TestCase.is_sample.is_(False))).scalars().all()
        samples = s.execute(select(TestCase).where(TestCase.problem_id == pid, TestCase.is_sample.is_(True))).scalars().all()
    assert body["hidden_test_count"] == len(hidden) > 0
    assert len(body["examples"]) == len(samples)
    for tc in hidden:
        if len(tc.input) > 12:  # long enough to be unambiguous
            assert tc.input.strip() not in r.text
            assert tc.expected_output.strip() not in r.text or len(tc.expected_output.strip()) < 6


def test_unknown_problem_404(client):
    r = client.get("/problems/does-not-exist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_cache_aside_hit_and_generation_invalidation(client):
    r = get_redis()
    gen = int(r.get(keys.CACHE_GENERATION) or 0)
    client.get("/problems/coin-change")
    key = keys.cache_problem(gen, "coin-change")
    assert r.exists(key) and 0 < r.ttl(key) <= 300
    r.set(key, r.get(key).replace("Coin Change", "Coin Change (cached)"))
    assert client.get("/problems/coin-change").json()["title"] == "Coin Change (cached)"  # served from cache
    r.incr(keys.CACHE_GENERATION)  # what the seed / admin invalidation does
    assert client.get("/problems/coin-change").json()["title"] == "Coin Change"


def test_health_ready_metrics(client):
    assert client.get("/health").json() == {"status": "ok"}
    ready = client.get("/ready").json()
    assert ready["checks"]["postgres"]["ok"] and ready["checks"]["redis"]["ok"]
    m = client.get("/metrics").text
    assert "codeforge_http_requests_total" in m and "codeforge_queue_backlog" in m
