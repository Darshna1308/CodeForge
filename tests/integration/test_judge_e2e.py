"""Real judging through the queue, workers and sandbox."""

import concurrent.futures as cf
import uuid

import pytest

from helpers import post_respecting_rate_limit, solution, sse_events, submit, wait_for

PY_SLUGS = [
    "two-sum", "valid-parentheses", "binary-search", "maximum-subarray", "merge-intervals",
    "longest-unique-substring", "number-of-islands", "shortest-path", "coin-change", "lru-cache",
]
CPP_SLUGS = ["two-sum", "valid-parentheses", "maximum-subarray", "number-of-islands", "shortest-path", "coin-change", "lru-cache"]


@pytest.mark.parametrize("slug", PY_SLUGS)
def test_python_reference_solutions_are_accepted(client, slug):
    sub = submit(client, slug, "python", solution(slug, "python"))
    d = wait_for(client, sub["id"])
    assert d["verdict"] == "ACCEPTED", (slug, d["results"][-3:], d["error_message"])
    assert d["tests_passed"] == d["tests_total"] > 3


@pytest.mark.parametrize("slug", CPP_SLUGS)
def test_cpp_reference_solutions_are_accepted(client, slug):
    sub = submit(client, slug, "cpp", solution(slug, "cpp"))
    d = wait_for(client, sub["id"])
    assert d["verdict"] == "ACCEPTED", (slug, d["compile_output"], d["results"][-3:])
    assert d["compile_ms"] is not None


def test_wrong_answer_stops_at_first_failure_and_hides_hidden_output(client):
    d = wait_for(client, submit(client, "maximum-subarray", "python", "input()\nprint(0)\n")["id"])
    assert d["verdict"] == "WRONG_ANSWER"
    failed = next(r for r in d["results"] if r["verdict"] == "WRONG_ANSWER")
    after = [r for r in d["results"] if r["ordinal"] > failed["ordinal"]]
    assert all(r["verdict"] == "SKIPPED" for r in after)
    for r in d["results"]:
        if not r["is_sample"]:
            assert r["input"] is None and r["expected_output"] is None and r["stdout"] is None and r["stderr"] is None


def test_compilation_error(client):
    d = wait_for(client, submit(client, "two-sum", "cpp", "int main() { return x; }")["id"])
    assert d["verdict"] == "COMPILATION_ERROR"
    assert "error" in d["compile_output"]
    assert d["results"] == []


def test_cpp_infinite_loop_is_time_limited(client):
    d = wait_for(client, submit(client, "two-sum", "cpp", "int main(){ while(true){} }")["id"])
    assert d["verdict"] == "TIME_LIMIT_EXCEEDED"


def test_python_infinite_loop_is_time_limited(client):
    d = wait_for(client, submit(client, "two-sum", "python", "while True:\n    pass\n")["id"])
    assert d["verdict"] == "TIME_LIMIT_EXCEEDED"


def test_runtime_error_segfault(client):
    d = wait_for(client, submit(client, "two-sum", "cpp", "int main(){ volatile int *p = 0; *p = 1; }")["id"])
    assert d["verdict"] == "RUNTIME_ERROR"
    assert d["results"][0]["signal"] == 11


def test_memory_limit(client):
    src = "x = bytearray(1024 * 1024 * 1024)\nprint(len(x))\n"
    d = wait_for(client, submit(client, "two-sum", "python", src)["id"])
    assert d["verdict"] == "MEMORY_LIMIT_EXCEEDED"


def test_output_flood_is_cut_off(client):
    d = wait_for(client, submit(client, "two-sum", "python", "while True:\n    print('x' * 4096)\n")["id"])
    assert d["verdict"] == "OUTPUT_LIMIT_EXCEEDED"


def test_run_mode_uses_samples_and_returns_output(client):
    r = post_respecting_rate_limit(client, "/executions", {"problem_slug": "two-sum", "language": "python", "source_code": solution("two-sum", "python")})
    assert r.status_code == 202
    d = wait_for(client, r.json()["id"])
    assert d["mode"] == "RUN" and d["verdict"] == "ACCEPTED"
    assert all(t["is_sample"] and t["stdout"] is not None and t["expected_output"] is not None for t in d["results"])


def test_run_mode_custom_input(client):
    r = post_respecting_rate_limit(client, "/executions", {"problem_slug": "two-sum", "language": "python",
                                                           "source_code": "print(sum(map(int, input().split())))", "custom_input": "40 2\n"})
    d = wait_for(client, r.json()["id"])
    assert d["verdict"] == "EXECUTED"
    assert d["results"][0]["stdout"].strip() == "42"


def test_sse_streams_lifecycle_in_order(client):
    sub = submit(client, "coin-change", "cpp", solution("coin-change", "cpp"))
    events = sse_events(client, sub["id"])
    names = [e for e, _ in events]
    assert names[0] == "snapshot"
    assert names[-1] == "end"
    for expected in ("claimed", "sandbox_ready", "compiled", "running", "test", "completed"):
        assert expected in names, names
    order = [n for n in names if n in ("claimed", "sandbox_ready", "compiled", "running", "completed")]
    assert order == ["claimed", "sandbox_ready", "compiled", "running", "completed"]
    completed = dict(events)["completed"]
    assert completed["verdict"] == "ACCEPTED"


def test_idempotency_key_under_concurrency(client):
    """Ten concurrent POSTs with one Idempotency-Key create exactly one submission."""
    key = f"e2e-{uuid.uuid4().hex}"
    src = solution("valid-parentheses", "python")
    with cf.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: submit(client, "valid-parentheses", "python", src, **{"Idempotency-Key": key}), range(10)))
    ids = {r["id"] for r in results}
    assert len(ids) == 1
    assert sum(1 for r in results if not r["idempotent_replay"]) == 1
    d = wait_for(client, ids.pop())
    assert d["verdict"] == "ACCEPTED"
    assert len(d["attempts"]) == 1  # judged exactly once


def test_transitions_follow_state_machine(client):
    d = wait_for(client, submit(client, "two-sum", "cpp", solution("two-sum", "cpp"))["id"])
    path = [t["to_status"] for t in d["transitions"]]
    assert path == ["CREATED", "QUEUED", "PROCESSING", "COMPILING", "RUNNING", "JUDGING", "COMPLETED"]


def test_other_users_cannot_read_submission(client, api_url):
    import httpx

    sub = submit(client, "two-sum", "python", "print(0)")
    other = httpx.Client(base_url=api_url)
    name = f"e2e_{uuid.uuid4().hex[:10]}"
    token = other.post("/auth/register", json={"username": name, "email": f"{name}@example.com", "password": "another-password"}).json()["access_token"]
    r = other.get(f"/submissions/{sub['id']}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404
