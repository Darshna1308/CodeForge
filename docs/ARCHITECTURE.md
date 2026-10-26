# Architecture

CodeForge is a monorepo with three deployable services, one shared library and one
sandbox image:

| Component | Path | Role |
|---|---|---|
| **web** | `apps/web` | Next.js 16 + TypeScript + Tailwind v4 + Monaco. Problem explorer, workspace, live execution visualizer, dashboard, architecture page. |
| **api** | `apps/api` | FastAPI. Auth, problems (cache-aside), submission intake (outbox + enqueue), submission reads, SSE realtime gateway, health/readiness, Prometheus metrics, stats. Never executes user code. |
| **worker** | `apps/worker` | Queue consumers (Redis Streams consumer group), sandbox driver, judge, leader-elected sweeper, heartbeat registry, Prometheus metrics on `:9100`. |
| **core** | `packages/core` | Shared SQLAlchemy models, submission state machine, transactional transition helper, queue + event wire formats, language adapters, settings, structured logging. |
| **sandbox image** | `infrastructure/sandbox` | Toolchains (Python 3.12, GCC 14), the trusted runner (`runner.py`) and privilege-dropping launcher (`launcher.c`). |

Infrastructure: PostgreSQL 16 (source of truth) and Redis 7 (queue, events, cache,
rate limits, liveness), orchestrated with Docker Compose.

## Request path

```
Browser ──POST /submissions──► API ──INSERT (CREATED)──► PostgreSQL
                               │  ──XADD cf:q:submit──► Redis Streams
                               │  ──UPDATE → QUEUED───► PostgreSQL
   ◄──202 {id, events_url}─────┘

Worker ──XREADGROUP──► Redis      (consumer group "judges")
   │──SELECT … FOR UPDATE; QUEUED→PROCESSING, attempt+1, lease──► PostgreSQL
   │──docker run -i --network none … codeforge-sandbox──► Sandbox container
   │       init {source, limits} ─► compile as uid 65534 ─► {"compiled"}
   │       run {input}           ─► execute under rlimits ─► {"result": stdout, rusage}
   │   (judge each output in the worker; renew lease; stop at first failure)
   │──fenced JUDGING→COMPLETED + results + attempt row (one transaction)──► PostgreSQL
   │──XACK──► Redis
   └──XADD cf:sub:{id}:events (claimed, sandbox_ready, compiled, test, completed…)──► Redis

Browser ◄──SSE (text/event-stream)── API ◄──XREAD BLOCK cf:sub:{id}:events── Redis
```

## Why this shape

* **API and execution are separated by a queue.** The API is latency-sensitive and
  must stay up; execution is slow, bursty and dangerous. The queue provides
  backpressure and lets the worker pool scale independently (`make worker WORKERS=4`).
* **PostgreSQL is the single source of truth.** Redis holds only reconstructible or
  recoverable state. Every correctness-critical decision (who owns a job, whether a
  result may be written) is a row-locked state transition in Postgres.
* **The worker is trusted; the sandbox is not.** The worker controls Docker; the
  submitted program runs in a sibling container with no Docker access, no network
  and no expected outputs (see [SECURITY.md](SECURITY.md)).

## Component details

* Submission lifecycle and judging: [EXECUTION_ENGINE.md](EXECUTION_ENGINE.md)
* Queue semantics, idempotency, recovery: [QUEUE_AND_CONCURRENCY.md](QUEUE_AND_CONCURRENCY.md)
* Schema and indexes: [DATABASE.md](DATABASE.md)
* Endpoints: [API.md](API.md)
* Threat model: [SECURITY.md](SECURITY.md)
* Decisions: [adr/](adr/)

## Observability

* **Structured JSON logs** (`codeforge_core/logging.py`): every line carries
  `service`, and when relevant `request_id` (from/echoed as `X-Request-ID`),
  `submission_id`, `worker_id`, `attempt`, `duration_ms`, `verdict`. Context flows via
  `contextvars`. Source code, test data and tokens are never logged.
* **Prometheus**: API `GET /metrics` (HTTP latency histograms by route template,
  cache hit/miss, rate-limit rejections, enqueue failures, SSE connections, and
  scrape-time gauges for queue backlog/in-flight and live workers). Each worker serves
  `:9100/metrics` (job outcomes, verdicts by language, job/queue-wait/sandbox-start/
  compile histograms, duplicates, redeliveries, dead letters, busy slots, sweeper actions).
* **Health**: `GET /health` (liveness, no dependencies) and `GET /ready` (Postgres +
  Redis round-trips with latencies; 503 when degraded).
* **Dashboard** (`/dashboard`): live queue depth (XINFO GROUPS), worker heartbeats,
  counters, 24h latency averages/p95 from `execution_attempts`, hourly submissions,
  verdict distribution, recent jobs. Nothing is synthesised.

## Failure handling summary

| Failure | Behaviour |
|---|---|
| Syntax / compile error | `COMPILATION_ERROR`, compiler output stored (16 KB cap) |
| Crash, segfault, non-zero exit | `RUNTIME_ERROR` with exit code / signal |
| Infinite loop | `TIME_LIMIT_EXCEEDED` (RLIMIT_CPU → SIGXCPU, or wall clock 2·TL+1s) |
| Excess memory | `MEMORY_LIMIT_EXCEEDED` (RLIMIT_AS refusal or peak RSS > limit; cgroup backstop) |
| Output flood | `OUTPUT_LIMIT_EXCEEDED`; program killed when the cap is crossed |
| Malformed request | 422 with field-level details; 413 for oversized source/input |
| Redis down at submit | Row stays `CREATED` (outbox); 202 returned; sweeper publishes later |
| Redis down for readers | Cache and rate limiter fail open; SSE degrades to DB polling |
| Postgres down | 503 `database_unavailable` with `Retry-After`; workers leave messages pending |
| Worker crash | Message reclaimed by XAUTOCLAIM; lease expiry → sweeper re-queues (max 3 attempts) |
| Sandbox start failure | Attempt marked FAILED, exponential backoff re-queue, `INTERNAL_ERROR` after 3 |
| Duplicate messages | Claim transition fails for all but one consumer → counted and ACKed |
| Poison message | Dead-lettered to `cf:q:dead` after 5 deliveries |
