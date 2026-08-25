---
adr: 0003
title: Stateless JSON streamable-http as the only MCP transport
status: Accepted
date: 2026-08-22
---

## Context

The primary external client is ChatGPT's connector mode. Early SSE-based
transports caused connection issues: open streams, session mapping complexity,
and responses that ChatGPT's client did not consume reliably (commits
6d3e903, 35d399b).

## Decision

Serve exactly one transport: streamable-http with JSON responses and stateless
mode forced on (`app/mcp_server.py`). Every POST is self-contained; no
`mcp-session-id` is issued; no server-side SSE stream stays open.

## Consequences

- Clients (including load generators) can fire bare tool-call POSTs without an
  initialize handshake per worker.
- Session-affinity features are out of scope by design; horizontal scaling does
  not need sticky routing.
- `/debug/transport` exists to verify loopback-only what transport actually runs.
