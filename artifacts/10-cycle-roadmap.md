# 10-Cycle Major Improvement Roadmap

The earlier micro-fix reports are provisional findings and do not count as complete cycles. Each official cycle below must execute the full chain:

`ASSESS → PLAN → IMPLEMENT → VERIFY → SECURITY_TEST → REMEDIATION_PLAN → FIX → REASSESS`

## Cycle 01 — Core correctness and API semantics
Unify command parsing, file conflict errors, REST command-result semantics, rate-limit metrics, and concurrent limiter behavior. Deliver a coherent error/metrics correctness layer with regression coverage.

## Cycle 02 — CLI architecture and packaging reliability
Audit the entire `bqa` command tree, remove wrapper/path fragility, validate global option behavior, standardize output/exit codes, improve install/uninstall workflow, and add subprocess-level integration tests.

## Cycle 03 — Server/tunnel lifecycle reliability
Harden supervisor adoption, stale PID cleanup, atomic state files, server-only restart guarantees, crash recovery, idempotent start, stop ordering, and isolated lifecycle regression.

## Cycle 04 — Filesystem security boundary
Deep-review path resolution, traversal, symlink races/escape, file type checks, line/byte boundaries, atomic writes, and permission/error behavior. Add adversarial local tests.

## Cycle 05 — Command execution and policy hardening
Improve shell command identity extraction, destructive-pattern detection, allowlist semantics, environment handling, timeout/process-group cleanup, output bounds, and audit fidelity.

## Cycle 06 — REST/MCP contract consistency
Create a shared error taxonomy, align REST and MCP responses, validate OpenAPI against behavior, cover all endpoints and negative paths, and remove semantic mismatches.

## Cycle 07 — Observability and audit quality
Harden metrics counting, structured audit records, latency/error classifications, secret redaction, log rotation/readability, and doctor diagnostics.

## Cycle 08 — Performance, concurrency, and resilience
Benchmark local/public paths, test concurrent file/command/API calls, assess memory/output limits, verify rate limiting under load, and improve bottlenecks found in repo code.

## Cycle 09 — Operations, recovery, and documentation
Improve install/update/restart/recovery procedures, configuration validation, shell completion, troubleshooting, rollback guidance, and operator documentation.

## Cycle 10 — Final full-system audit and release readiness
Run a clean baseline, complete regression matrix, source security review, dependency review using available tools, public/local smoke tests, diff audit, documentation reconciliation, and final blocker/risk report.

## Reporting rule
Each official cycle produces eight artifacts under `artifacts/cycle-XX/` and a visible report only after all eight phases complete.
