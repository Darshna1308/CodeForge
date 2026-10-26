"""End-to-end tests against a *running* stack (API + worker + sandbox).

    make up            # or run api/worker locally
    make test-e2e      # CODEFORGE_API_URL defaults to http://localhost:8000

These tests submit real programs, which are executed by real workers in real
sandbox containers. Nothing is mocked.
"""

import os
import uuid

import httpx
import pytest

API = os.environ.get("CODEFORGE_API_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def api_url() -> str:
    try:
        httpx.get(f"{API}/ready", timeout=3).raise_for_status()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"CodeForge API not reachable at {API}: {exc}")
    return API


@pytest.fixture(scope="session")
def client(api_url) -> httpx.Client:
    c = httpx.Client(base_url=api_url, timeout=30)
    name = f"e2e_{uuid.uuid4().hex[:10]}"
    r = c.post("/auth/register", json={"username": name, "email": f"{name}@example.com", "password": "correct-horse-battery"})
    r.raise_for_status()
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    yield c
    c.close()
