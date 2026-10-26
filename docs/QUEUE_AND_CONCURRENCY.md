# Queue, concurrency and recovery

## Redis keys

| Key | Type | Purpose | TTL |
|---|---|---|---|
| `cf:q:run` | Stream + group `judges` | "Run Code" jobs (priority) | MAXLEN ~100k |
| `cf:q:submit` | Stream + group `judges` | judged submissions | MAXLEN ~100k |
| `cf:q:dead` | Stream | dead-lettered jobs (> 5 deliveries) | MAXLEN ~10k |
| `cf:sub:{id}:events` | Stream | lifecycle events for SSE | 1 h, MAXLEN ~500 |
| `cf:worker:{worker_id}` | Hash | liveness heartbeat | 15 s, refreshed every 5 s |
| `cf:lock:sweeper` | String | sweeper leader lease (random token) | 3 × interval |
| `cf:stats:*` | Counter | jobs completed/failed, duplicates, redeliveries | — |
| `cf:cache:problems:gen` | Counter | cache generation | — |
| `cf:cache:problems:v{gen}:list:{sha1(filters)}` | String (JSON) | problem list per filter | 120 s |
| `cf:cache:problems:v{gen}:detail:{slug}` | String (JSON) | problem detail (samples only) | 300 s |
| `cf:cache:stats:{overview,system,leaderboard}` | String (JSON) | dashboard aggregates | 10 / 3 / 30 s |
| `cf:rl:{bucket}:{subject}` | Hash | token bucket state | refill time + 1 s |
| `cf:auth:revoked:{jti}` | String | logged-out tokens | until token expiry |

## Why Redis Streams (and not a library)

Streams with consumer groups give exactly the semantics a judge needs, with no hidden
behaviour (see [ADR 0002](adr/0002-redis-streams-queue.md)):

* **XADD** appends a job.
* **XREADGROUP … >** hands each new entry to *one* consumer of the group and records
  it in the group's **Pending Entries List (PEL)**.
* **XACK** removes it from the PEL once the job is fully handled.
* A consumer that dies leaves its entries in the PEL. **XAUTOCLAIM** with
  `min-idle-time = visibility timeout (180 s)` lets another consumer take them over;
  XPENDING exposes the **delivery count** used for dead-lettering.

This is **at-least-once delivery**. Duplicates are normal; exactly-once *effects* come
from the database.

## Submission intake: transactional outbox

```
API:  INSERT submission (CREATED) + audit row; COMMIT     ← durable before anything else
      XADD cf:q:submit {submission_id}                   ← may fail (Redis down)
      UPDATE CREATED → QUEUED (row lock);  COMMIT
      return 202 {id, events_url}
```

* If XADD fails, the API still returns 202 with status `CREATED`. The row *is* the
  outbox entry; the sweeper publishes it after a 10 s grace period.
* If a fast worker receives the message before the API flips the row to `QUEUED`, the
  worker completes the `CREATED → QUEUED` flip itself (the message proves it was
  published) and then claims it. Without this, the race would silently drop work.

### Idempotent creation

`POST /submissions` and `/executions` accept `Idempotency-Key` (8–64 chars). A partial
unique index `uq_submissions_user_idempotency (user_id, idempotency_key) WHERE key IS NOT NULL`
makes concurrent retries collide in the database; the loser catches the
`IntegrityError` and returns the original submission with `200` and
`idempotent_replay: true`. The web client sends one key per click and reuses it on
network retries. Tested with 8–10 concurrent requests: exactly one row, one XADD.

## Claim: one winner per job

```sql
BEGIN;
SELECT status, worker_id, attempt FROM submissions WHERE id = $1 FOR UPDATE;
-- legal only if status = 'QUEUED'
UPDATE submissions
   SET status='PROCESSING', worker_id=$w, attempt=attempt+1,
       lease_expires_at=now()+'90s', started_at=now()
 WHERE id=$1 AND status='QUEUED';
INSERT INTO submission_transitions …; INSERT INTO execution_attempts …;
COMMIT;
```

Concurrent claimers block on the row lock; when the winner commits, the others
re-read the row (READ COMMITTED returns the latest committed version to `FOR UPDATE`),
see `PROCESSING`, and give up. They count a *duplicate delivery* and XACK. Tested by
`test_concurrent_claims_exactly_one_wins` (20 threads, one winner).

## Leases and fencing tokens

* A claim sets `lease_expires_at = now + LEASE_SECONDS (90 s)`; the worker renews it
  after every test.
* `attempt` doubles as a **fencing token**. Every write after the claim — status
  moves, lease renewals, the final result commit — is conditioned on
  `(worker_id, attempt)` still matching. If a worker stalls (GC pause, partition,
  `SIGSTOP`) past its lease, the sweeper re-queues the job, another worker claims
  `attempt + 1`, and every late write from the stale worker fails. The stale worker
  notices (`LostLease`), records `LOST_LEASE` on its attempt row and stops without
  writing results. The final commit (results + COMPLETED + attempt row) is one
  transaction, so a fenced-out worker can never leave partial results.

## Recovery paths

| Failure | Detected by | Action |
|---|---|---|
| Worker process dies mid-job | lease expiry (sweeper) | attempt → `ABANDONED`; row → `QUEUED` and re-published, or → `INTERNAL_ERROR` once `attempt ≥ MAX_ATTEMPTS (3)` |
| Worker dies after XREADGROUP, before claim | XAUTOCLAIM after 180 s idle | another consumer processes it |
| Message lost (Redis restart w/o AOF) | sweeper: `QUEUED` with `queued_at` older than 10 min | re-publish (duplicates harmless) |
| API died between COMMIT and XADD | sweeper: `CREATED` older than 10 s | publish, flip to `QUEUED` |
| Sandbox cannot start / protocol breaks | worker (`SandboxError`) | attempt → `FAILED`; backoff `min(2^attempt, 10)` s; re-queue or `INTERNAL_ERROR` |
| Postgres unavailable mid-job | worker (`OperationalError`) | do **not** XACK; lease expiry + XAUTOCLAIM retry later |
| Redis unavailable | consumers | exponential backoff (1 → 15 s) and retry |
| Poison message | delivery count > 5 | XADD to `cf:q:dead`, XACK, row → `INTERNAL_ERROR` |
| Orphaned sandbox containers | worker start-up janitor | `docker rm -f` by label `codeforge.sandbox=1` |

Observed during development: two consumers crashed on a bug before ACKing; after
the visibility timeout the restarted worker logged
`recovered pending message from a stalled consumer` and judged both submissions.

## Sweeper leader election

Every worker process runs a sweeper thread, but only the holder of
`cf:lock:sweeper` acts. Acquisition is `SET key token NX PX 15000`; renewal is a Lua
compare-and-`PEXPIRE` so a process can only extend its *own* lease. The sweeper's
writes are ordinary guarded transitions, so even two sweepers overlapping during a
lock handover cannot corrupt state.

## Scheduling

Each worker runs `WORKER_CONCURRENCY` consumer threads (default 2). Each consumer:

1. Non-blocking read from `cf:q:run` (interactive jobs first).
2. Otherwise a blocking read (2 s) across `cf:q:submit` and `cf:q:run`.
3. After 4 consecutive RUN jobs, skip step 1 once (anti-starvation for submissions).

`XREADGROUP` with `COUNT 1` over two streams can return one entry *per stream*; the
consumer processes every returned entry (an earlier version only processed the
first, leaving the other pending until XAUTOCLAIM — caught in review).

Horizontal scaling: `make worker WORKERS=4` (or `docker compose up --scale worker=4`).

## Rate limiting

Token bucket per `(bucket, subject)` implemented as one Lua script: refill based on
Redis `TIME` (consistent across API replicas), spend one token or return the time
until the next token. Atomic, so concurrent requests cannot both take the last token.
Defaults: submit 10/60 s per user, run 20/60 s per user, auth 10/60 s per IP.

## Cache-aside

* Read: `GET`; on miss take `SET key:lock NX PX 3000`; the lock holder loads from
  Postgres and `SET … EX ttl`; concurrent missers poll the key for up to ~250 ms
  instead of stampeding the database.
* Invalidation: `INCR cf:cache:problems:gen` (seed and the admin endpoint do this).
  Keys embed the generation, so all old entries become unreachable atomically and
  expire via TTL. No `KEYS`/`SCAN` deletes.
* Personal data (per-user solved status) is merged *after* the cache lookup and never
  cached. Hidden tests never touch these paths.
* Redis errors → read-through to Postgres.
* Acceptance rates in the list are eventually consistent (≤ 120 s).

## Realtime (SSE)

`GET /submissions/{id}/events` (owner only):

1. `snapshot` event with the authoritative DB state.
2. Replay of `cf:sub:{id}:events` from the start, or from `Last-Event-ID` on reconnect
   (event ids are Redis Stream ids).
3. Tail with `XREAD BLOCK 15000`; `: heartbeat` comments keep idle proxies open.
4. Close after `completed`/`internal_error`/`cancelled` (+ a final snapshot and `end`),
   after 10 minutes, or when the client disconnects.
5. Redis unavailable → degrade to DB polling every second.

The browser uses `EventSource` (automatic reconnect with `Last-Event-ID`) and falls
back to REST polling if the stream cannot be established. The visualizer reducer is
idempotent, so replayed events are harmless.
