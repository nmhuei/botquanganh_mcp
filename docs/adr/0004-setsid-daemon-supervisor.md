---
adr: 0004
title: setsid daemonization with a shell supervisor loop
status: Accepted
date: 2026-08-21
---

## Context

`bqa start` must survive its parent exiting (terminal close, CI shell teardown).
Early versions died with the parent; a naive double-fork also left process-group
ambiguity between launcher, server, and cloudflared.

## Decision

Launch the runtime via `setsid ./scripts/start_tunnel_server.sh` (own session /
process group), supervised by a shell loop (`start_tunnel_server.sh`) that ticks
every 0.1s, respawns a dead server after a grace window, and health-checks
hourly. Stop paths target the process group and verify PID identity via
`/proc/<pid>/cmdline` before signaling (`scripts/process_helpers.sh`,
`app/cli/lifecycle.py`).

## Consequences

- Clean stop requires signaling the whole group, not a single PID — otherwise
  grandchildren survive.
- Lost cloudflared tunnels are NOT auto-recreated (quick tunnels get new URLs);
  the operator re-runs `bqa start` / the tunnel script.
- PID-file hygiene matters: every consumer verifies identity and start time
  before killing anything.
