---
adr: 0006
title: Hardening round 2 — bounded drains, honest readiness, serialized replace
status: Accepted
date: 2026-08-25
---

## Context

Strength/stress runs exposed several failure classes: commands whose detached
children kept the output pipes open could stall result delivery on the drain
joins; the CLI could print a tunnel URL that was never confirmed ready;
concurrent `replace_text_in_file` calls could lose updates because the
read-modify-write ran outside the lock; a storm of blocking REST handlers could
starve every endpoint on the default worker pool; two supervisors could race
past the PID-file check/write window; `run_mcp_tunnel.sh` exited 0 even when no
connector URL ever appeared; the stop script resolved `MCP_PORT` from `.env`
while start honored an exported value; and the inventory cache expired both
variants together; and `app/cli/context.py` silently hoists subcommand options
that reuse a global flag name.

## Decision

- Executor (`app/host/executor.py`): drain-thread stall handling reduced from
  5s/2s joins to 2s then 1s. If a drain thread is still alive after escalation,
  the result carries `output_incomplete: true`. Strays that stayed in the
  child's process group are still killed by the SIGTERM → SIGKILL escalation;
  children that escaped via their own `setsid()` cannot be reached and only tie
  up one drain thread and its pipe fds for that single call — documented
  tradeoff, no cross-call leak.
- CLI (`app/cli/main.py`): `bqa start` / `bqa restart` print the connector URL
  only when status reports `connector_ready`; the JSON payload gains a
  `runtime_ready` field; fabricating stale URLs is removed.
- `replace_text_in_file` (`app/host/files.py`): read-modify-write now runs
  under one flock on an O_RDWR fd, applied with ftruncate + write + fsync. A
  crash mid-write can leave truncated content — accepted tradeoff versus the
  lost-update bug.
- REST (`app/rest_api.py`): blocking handlers move off the shared default
  threadpool onto a dedicated `anyio.CapacityLimiter(16)` so command storms
  cannot freeze all endpoints; execution volume is still bounded by
  `CommandCapacity` (100).
- Supervisor (`scripts/start_tunnel_server.sh`): a mkdir-based lock directory,
  released by an EXIT trap, closes the double-supervisor TOCTOU around PID-file
  check and write.
- `run_mcp_tunnel.sh`: exits 1 when the connector URL never becomes ready
  (was exit 0).
- Stop script (`scripts/stop_tunnel_server.sh`): an exported `MCP_PORT` wins
  over `.env`, matching start-time precedence.
- Inventory cache TTL (`app/host/inventory.py`) is per-variant:
  `created_at:with_versions` and `created_at:without_versions` carry
  separately keyed timestamps instead of one shared `created_at`.
- CLI option parsing (`app/cli/context.py`): hoisting of global options is
  kept as-is; the collision — a subcommand-local option reusing a global flag
  name is lifted as global — is documented as a known limitation, so
  subcommand options must not reuse global flag names.

## Consequences

- Callers must treat `output_incomplete: true` as "output tail may be missing";
  worst-case call duration stays near timeout plus ~3 seconds instead of
  hanging on the joins.
- A replace interrupted by a crash can leave partial content; locking removes
  the concurrent lost-update class instead.
- Automation around `bqa start/restart` and `run_mcp_tunnel.sh` must interpret
  a non-zero exit or an absent URL line as "not ready", never re-read cached
  output as a live URL.
- Subcommands must pick option names disjoint from the global flags; reusing a
  global name silently changes scope of the parsed option.
