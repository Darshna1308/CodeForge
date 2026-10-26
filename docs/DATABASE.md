# Database

PostgreSQL 16, accessed through SQLAlchemy 2 (sync, psycopg 3). Schema is owned by
Alembic (`apps/api/alembic/versions/0001_initial_schema.py`); models live in
`packages/core/codeforge_core/models.py`. `alembic check` reports no drift between
models and migrations.

## Entities

```
users ─┐                        languages (reference data, seeded by migration)
       │ 1..*                        │
       ▼                             │ FK
   submissions ◄────────────────────┘
       │  │ 1..*            problems ──1..*── test_cases
       │  └──► submission_results ──► test_cases (nullable: custom input)
       │ 1..*                    │
       ├──► execution_attempts   └──*..*── tags  (via problem_tags)
       └──► submission_transitions (append-only audit)
```

| Table | Notes |
|---|---|
| `users` | `username`, `email` unique **case-insensitively** via expression indexes on `lower()`; CHECK on username format; `role` enum (`USER`/`ADMIN`); Argon2id hash. |
| `problems` | slug (CHECK kebab-case, unique), difficulty enum, statement/spec text, `time_limit_ms` CHECK 100–10000, `memory_limit_mb` CHECK 16–1024. |
| `tags`, `problem_tags` | many-to-many; composite PK + index on `tag_id` for tag filters. |
| `test_cases` | `(problem_id, ordinal)` unique; `is_sample` separates public examples from hidden tests; expected outputs computed by reference solutions at seed time. |
| `languages` | FK target for `submissions.language`, so an unknown language cannot be stored even by a buggy client of the DB. |
| `submissions` | lifecycle `status` enum, `verdict` enum, lease (`worker_id`, `attempt`, `lease_expires_at`), timestamps for each phase, aggregates (`runtime_ms`, `memory_kb`, `tests_passed/total`), compiler output, error message. |
| `submission_results` | one row per test per submission (`(submission_id, ordinal)` unique), per-test verdict, cpu/wall ms, peak RSS, exit code, signal; stdout/stderr only for public data. |
| `execution_attempts` | one row per claim: worker, outcome (`RUNNING`/`SUCCEEDED`/`FAILED`/`ABANDONED`/`LOST_LEASE`), queue wait, sandbox start, compile, total ms. Feeds the dashboard and makes retries visible. |
| `submission_transitions` | append-only audit of every state change: from, to, attempt, actor (`api`, worker id, `sweeper@…`, `user:…`). |

JSON columns: none. Everything has a relational shape; per-test data is a table, not
a blob, so it can be indexed and aggregated.

## Constraints that encode invariants

* `ck_submissions_verdict_iff_completed`: `(status = 'COMPLETED') = (verdict IS NOT NULL)`.
* `ck_submissions_source_size` / `ck_submissions_input_size`: ≤ 64 KiB (`octet_length`),
  backing the API's validation.
* `ck_submissions_attempt_nonneg`.
* Foreign keys with `ON DELETE CASCADE` from children to submissions/problems, and
  `SET NULL` from results to test cases (re-seeding tests keeps old results).

## Indexes and the queries they serve

| Index | Query |
|---|---|
| `ix_submissions_user_created (user_id, created_at DESC)` | "my submissions, newest first" (history page) |
| `ix_submissions_problem_mode_verdict` | per-problem acceptance counts |
| `ix_submissions_user_problem_verdict` | per-user solved/attempted status in the problem list |
| `ix_submissions_created_at` | dashboard hourly series |
| `ix_submissions_live (status, lease_expires_at) WHERE status IN (live states)` | sweeper scans; **partial**, so it stays tiny as history grows |
| `uq_submissions_user_idempotency (user_id, idempotency_key) WHERE key IS NOT NULL` | idempotent creation; partial so NULL keys don't collide |
| `uq_test_cases_problem_ordinal`, `ix_test_cases_problem_sample` | loading samples vs all tests |
| `ix_execution_attempts_started` | dashboard latency window |
| `ix_submission_transitions_submission (submission_id, id)` | audit trail per submission |

## Transactions

* Short, explicit units of work (`sessionmaker.begin()`); no transaction spans a
  sandbox execution.
* State changes: row lock + guarded UPDATE + audit insert in one transaction
  (`repository.transition`).
* Result commit: COMPLETED transition (fenced) + delete/insert results + attempt row
  update in one transaction — all or nothing.
* Isolation level: READ COMMITTED (default). Correctness relies on row locks and
  conditional updates, not on SERIALIZABLE retries.
* Connection pool: `pool_pre_ping` so a Postgres restart surfaces as at most one
  retried connection, not a burst of errors; DB errors map to HTTP 503.

## Migrations and seeding

```
make migrate     # alembic upgrade head
make seed        # idempotent upsert of 10 problems, regenerates tests, bumps cache generation
```

Seeding is deterministic (fixed RNG seed per problem). Test inputs come from
generators that include edge cases (empty-ish inputs, all-negative arrays, touching
intervals, 64-bit distances, winding islands that defeat naive recursion) and large
performance cases (10^5 elements).
