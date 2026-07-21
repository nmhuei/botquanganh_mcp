# Implementation Plan — Official Cycle 05

## Goal
Make host command execution bounded, deterministic, credential-aware, and auditable.

## Tasks
1. Strip shell injection variables always and redact credential-like environment variables unless explicitly allowlisted.
2. Use a non-login, no-profile shell.
3. Replace temporary output files with continuously drained, bounded stdout/stderr collectors.
4. Centralize process-group termination and verify descendants do not survive timeout.
5. Split single-background chains, expand privilege-boundary detection, and reject dynamic shell constructs in allowlist mode.
6. Reload only the bridge and verify policy, environment redaction, timeout, and public health.

## Acceptance criteria
- Credentials are absent from child commands by default.
- Explicitly allowlisted custom variables remain available.
- Shell startup hooks do not execute.
- Dual-stream multi-megabyte output remains bounded without deadlock.
- Timeout removes background descendants.
- Policy identifies background chains and rejects dynamic allowlist constructs.
- Tunnel PID and URL remain unchanged.
