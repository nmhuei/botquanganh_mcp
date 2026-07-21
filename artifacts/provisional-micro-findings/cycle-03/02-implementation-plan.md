# Implementation Plan — Cycle 03

## TASK-001 — Preserve command exit semantics
Map result envelopes containing `exit_code` and no service error to HTTP 200. Add regression coverage. Keep policy, timeout and schema errors mapped to their existing HTTP statuses.
