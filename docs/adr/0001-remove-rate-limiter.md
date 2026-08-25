---
adr: 0001
title: Remove the HTTP rate limiter; rely on command capacity gating
status: Accepted
date: 2026-08-24
---

## Context

An early version carried an HTTP-layer rate limiter alongside `CommandCapacity`
(executor-level bound on concurrent child commands). Two throttles meant two
places to reason about backpressure, and the HTTP limiter produced 429s that the
error contract advertised but real clients never handled well.

## Decision

Remove the rate limiter entirely (commit 0c814a7). Backpressure is enforced only
by `CommandCapacity` (`app/host/executor.py`): at most `MAX_CONCURRENT_COMMANDS`
(default 100) child commands run concurrently; excess callers queue up to
`COMMAND_QUEUE_TIMEOUT_SECONDS` (2s) and then receive `SERVICE_BUSY` / 503.

## Consequences

- Single choke point, single timeout semantic; easier to strength-test.
- Cheap read-only MCP calls are no longer throttled — acceptable because they do
  not spawn processes.
- The error contract still lists 429 for compatibility but it is no longer
  emitted by capacity pressure.
