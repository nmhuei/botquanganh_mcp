# Implementation Plan — Official Cycle 01

## Goal
Establish correct and observable semantics for command identity, expected conflicts, command result transport, and rate limiting.

## Scope
`app/host/policy.py`, `app/security.py`, `app/rest_api.py`, `app/mcp_server.py`, `app/ratelimit.py`, and related tests.

## Non-goals
No auth behavior change, no tunnel restart, no breaking API schema redesign.

## Task dependency graph
TASK-001 and TASK-002 are independent. TASK-003 depends on REST semantics. TASK-004 and TASK-005 form the rate-limit workstream.

### TASK-001 — Quote-aware shell chain identity
- Priority: High
- Objective: identify actual commands without splitting separators inside quotes.
- Acceptance: valid quoted separators produce one command name; real chains still split.
- Tests: parser and full policy regression.

### TASK-002 — Stable expected-conflict error
- Priority: Medium
- Objective: map `FileExistsError` to `FILE_EXISTS` through MCP.
- Acceptance: clients can distinguish conflict from internal failure.

### TASK-003 — Preserve command exit semantics over REST
- Priority: High
- Objective: return HTTP 200 for a completed command exchange even when exit code is non-zero.
- Acceptance: body keeps `ok=false` and real `exit_code`; service errors retain error statuses.

### TASK-004 — Record rate-limit rejections
- Priority: High
- Objective: increment `rate_limit_hits` at every 429 rejection.
- Acceptance: ASGI regression observes one increment and no downstream call.

### TASK-005 — Make limiter state concurrency-safe
- Priority: High
- Objective: serialize cleanup/check/append and use monotonic time.
- Acceptance: exactly configured number of concurrent requests pass; wall-clock changes cannot affect the window.

## Verification matrix
| Requirement | Evidence | Expected |
|---|---|---|
| Quote preservation | parser tests and direct probe | correct command names |
| File conflict taxonomy | public adapter test | `FILE_EXISTS` |
| Non-zero REST command | subprocess integration | HTTP 200 + exit code 1 |
| 429 metric | ASGI middleware test | one metric increment |
| Concurrency bound | 100-request threaded test | exactly 10 allowed |
| Clock safety | monkeypatched wall clock | monotonic path only |
