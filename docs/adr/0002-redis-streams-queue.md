# ADR 0002 — Redis Streams consumer groups as the job queue

**Status:** accepted

## Context
Execution must be asynchronous, survive worker crashes, support multiple workers and
make its delivery semantics explicit. Redis is already needed for caching, rate
limiting and realtime events.

## Decision
Implement the queue directly on Redis Streams: `XADD` to enqueue, one consumer group
(`judges`), `XREADGROUP` to receive, `XACK` on completion, `XAUTOCLAIM` (visibility
timeout 180 s) to recover messages from dead consumers, delivery counts from
`XPENDING` for dead-lettering. Two streams (`run`, `submit`) implement priority.

Exactly-once *effects* are provided by the database claim (ADR 0001), not by the queue.

## Consequences
* Delivery is at-least-once; duplicates are expected and cheap (one failed row lock).
* The PEL makes in-flight work observable (`XINFO GROUPS` → dashboard).
* ~200 lines of explicit queue code instead of a framework whose retry/ack semantics
  would need reverse-engineering.
* We own edge cases a library would hide, e.g. multi-stream `XREADGROUP` returning one
  entry per stream (handled; see QUEUE_AND_CONCURRENCY.md).

## Alternatives
* *Celery/RQ*: convenient but hides ack timing (`acks_late`, visibility timeouts) and
  couples job state to the broker.
* *Redis lists + BRPOPLPUSH*: reliable-queue pattern works but lacks consumer groups,
  delivery counts and per-consumer pending tracking.
* *Kafka/RabbitMQ*: excellent, but an extra heavyweight service for a single-node
  portfolio deployment.
* *Postgres `SKIP LOCKED` queue*: viable and simpler to make transactional; rejected to
  keep polling load off the primary database and to demonstrate stream semantics.
