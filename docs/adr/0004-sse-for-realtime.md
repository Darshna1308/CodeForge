# ADR 0004 — Server-Sent Events for realtime status

**Status:** accepted

## Context
The browser needs live status (queued → compiling → per-test results → verdict). The
data flows one way, server → client.

## Decision
Use SSE (`text/event-stream`) at `GET /submissions/{id}/events`, backed by a Redis
Stream per submission. Event ids are stream ids, so `Last-Event-ID` resumes exactly.

## Consequences
* Plain HTTP: works through proxies, uses the existing cookie auth (`withCredentials`),
  automatic browser reconnection.
* Replay is free: late subscribers get the full timeline, which the execution
  visualizer needs.
* One connection per watched submission; streams close at the terminal event (or after
  10 minutes), so connections are short-lived.
* Degrades to DB polling when Redis is down; the client falls back to REST polling.

## Alternatives
* *WebSockets*: bidirectional capability is unused; needs separate auth handshake and
  reconnection/replay logic.
* *Redis PUB/SUB*: fire-and-forget — a client that connects after the worker publishes
  misses events. Streams fix that.
* *Polling only*: simpler, but laggy and wasteful; kept only as the fallback.
