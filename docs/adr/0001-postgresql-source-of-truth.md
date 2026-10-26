# ADR 0001 — PostgreSQL as the single source of truth

**Status:** accepted

## Context
A judge must never lose a submission, never judge one twice in a way users can see,
and never attach results to the wrong attempt. Several actors write concurrently:
the API, N workers, the sweeper and users cancelling.

## Decision
All durable and correctness-critical state lives in PostgreSQL: users, problems, tests,
submissions (including lease and fencing token), per-test results, attempts and an
audit log. Status changes are row-locked, validated transitions.

## Consequences
* Relational constraints encode invariants (verdict iff completed, size limits,
  idempotency uniqueness, FK integrity) so bugs fail loudly instead of corrupting data.
* Row-level locking + READ COMMITTED gives simple, provable mutual exclusion for claims.
* Redis can lose data without losing submissions; the sweeper rebuilds queue state
  from Postgres.
* Postgres is on the hot path of every job (claim, renew, commit): a few small
  transactions per job, which is negligible next to sandbox start-up (~300–400 ms).

## Alternatives
* *Redis as the store*: fast, but no relational integrity or durable transactions.
* *MongoDB/document store*: per-test results and acceptance statistics are naturally
  relational and aggregated; joins and constraints matter here.
