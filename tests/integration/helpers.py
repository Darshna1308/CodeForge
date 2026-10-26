import json
import time
from pathlib import Path

import httpx

SOLUTIONS = Path(__file__).resolve().parents[1] / "fixtures" / "solutions"


def solution(slug: str, lang: str) -> str:
    return (SOLUTIONS / f"{slug}.{ 'py' if lang == 'python' else 'cpp'}").read_text()


def wait_for(client: httpx.Client, submission_id: int, timeout: float = 120) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        d = client.get(f"/submissions/{submission_id}").json()
        if d["status"] in ("COMPLETED", "INTERNAL_ERROR", "CANCELLED"):
            return d
        time.sleep(0.3)
    raise TimeoutError(f"submission {submission_id} did not finish")


def post_respecting_rate_limit(client: httpx.Client, path: str, body: dict, headers: dict | None = None) -> httpx.Response:
    """The API rate-limits submissions per user; honour Retry-After like a well-behaved client."""
    for _ in range(30):
        r = client.post(path, json=body, headers=headers or {})
        if r.status_code != 429:
            return r
        time.sleep(int(r.headers.get("Retry-After", "1")))
    return r


def submit(client: httpx.Client, slug: str, lang: str, source: str, **headers) -> dict:
    r = post_respecting_rate_limit(client, "/submissions", {"problem_slug": slug, "language": lang, "source_code": source}, headers)
    assert r.status_code in (200, 202), r.text
    return r.json()


def sse_events(client: httpx.Client, submission_id: int, timeout: float = 120) -> list[tuple[str, dict]]:
    """Consume the SSE stream until it ends; returns (event, data) pairs."""
    out: list[tuple[str, dict]] = []
    event = None
    with client.stream("GET", f"/submissions/{submission_id}/events", timeout=timeout) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        for line in resp.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: ") and event:
                out.append((event, json.loads(line[6:])))
                if event == "end":
                    break
    return out
