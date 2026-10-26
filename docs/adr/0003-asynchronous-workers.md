# ADR 0003 — Asynchronous worker pool, separate from the API

**Status:** accepted

## Context
Compiling + running a submission costs 0.5–5 s and executes untrusted code. Doing it
inside an HTTP request would tie up API capacity, make timeouts user-visible and put
untrusted execution next to secrets and the database connection pool.

## Decision
The API only validates, persists, enqueues and returns `202 Accepted` with an id.
Separate worker processes (own image, own scaling) consume jobs and drive sandboxes.
Results flow back via Postgres (state) and Redis (events).

## Consequences
* API latency is independent of execution time; bursts become queue depth, visible on
  the dashboard, instead of failed requests.
* Workers scale horizontally (`--scale worker=N`) and can be drained gracefully
  (SIGTERM → finish in-flight jobs).
* Clients need a status channel → SSE (ADR 0004).
* More moving parts: recovery logic (leases, sweeper) is required and implemented.
