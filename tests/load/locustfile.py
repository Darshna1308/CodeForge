"""Load scenarios for CodeForge.

    ReaderUser    — anonymous browsing: problem list + details (exercises cache-aside)
    SubmitterUser — authenticated users submitting real solutions and polling for verdicts
                    (exercises the queue, worker pool and sandbox end to end)

Run headless via tests/load/run.sh, which records environment info with the results.
Rate limits apply per user, so each simulated submitter registers its own account.
"""

import random
import time
import uuid
from pathlib import Path

from locust import HttpUser, between, events, task

SOLUTIONS = Path(__file__).resolve().parents[1] / "fixtures" / "solutions"
SLUGS = ["two-sum", "valid-parentheses", "binary-search", "maximum-subarray", "coin-change", "lru-cache"]


class ReaderUser(HttpUser):
    weight = 3
    wait_time = between(0.2, 1.0)

    @task(3)
    def list_problems(self):
        self.client.get("/problems", name="/problems")

    @task(5)
    def problem_detail(self):
        self.client.get(f"/problems/{random.choice(SLUGS)}", name="/problems/[slug]")

    @task(1)
    def overview(self):
        self.client.get("/stats/overview", name="/stats/overview")


class SubmitterUser(HttpUser):
    weight = 1
    wait_time = between(1, 3)

    def on_start(self):
        name = f"load_{uuid.uuid4().hex[:10]}"
        r = self.client.post("/auth/register", json={"username": name, "email": f"{name}@example.com", "password": "load-test-password"},
                             name="/auth/register")
        self.client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        self.client.cookies.clear()

    @task
    def submit_and_wait(self):
        slug = random.choice(SLUGS)
        lang = random.choice(["python", "cpp"]) if (SOLUTIONS / f"{slug}.cpp").exists() else "python"
        src = (SOLUTIONS / f"{slug}.{'py' if lang == 'python' else 'cpp'}").read_text()
        start = time.perf_counter()
        r = self.client.post("/submissions", json={"problem_slug": slug, "language": lang, "source_code": src}, name="/submissions")
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", "5")))
            return
        if r.status_code != 202:
            return
        sid = r.json()["id"]
        deadline = time.time() + 180
        while time.time() < deadline:
            time.sleep(0.5)
            d = self.client.get(f"/submissions/{sid}", name="/submissions/[id] (poll)").json()
            if d["status"] in ("COMPLETED", "INTERNAL_ERROR", "CANCELLED"):
                # Custom metric: true submit-to-verdict latency as seen by a client.
                events.request.fire(request_type="JUDGE", name=f"submit→verdict ({d['verdict']})",
                                    response_time=(time.perf_counter() - start) * 1000, response_length=0,
                                    exception=None if d["verdict"] == "ACCEPTED" else Exception(d["verdict"] or d["status"]),
                                    context={})
                return
