# Implementation Plan — Official Cycle 09

## Goal
Create one repeatable operations, validation, diagnostics, recovery, and rollback workflow.

## Tasks
1. Expand CLI configuration defaults and validate every boolean/numeric/resource limit.
2. Enforce secure `.env` permissions when credentials are present.
3. Validate MCP path, workspace, knowledge catalog, executables, global CLI ownership, audit storage, disk space, and process identity.
4. Add `doctor --strict`, `doctor --local-only`, and `config validate --strict`.
5. Add a unified quality gate with source, tests, static, dependency-closure, config, and optional runtime/full modes.
6. Add a redacted diagnostics collector excluding `.env` and log bodies.
7. Add project dependency-closure validation that reports foreign packages separately.
8. Replace the old test entry point with the quality gate.
9. Write an operations/recovery/rollback/production runbook and README entry points.
