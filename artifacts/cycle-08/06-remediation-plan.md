# Remediation Plan — Official Cycle 08

- REM-032: enforce a semaphore-like command capacity before process creation.
- REM-033: bound queue wait and return `SERVICE_BUSY` with HTTP 503.
- REM-034: cap tracked rate-limit clients and reject new clients if no stale state can be pruned.
- REM-035: use deques and incremental expiry rather than rebuilding timestamp lists.
- Add capacity telemetry and deterministic load tests.
- Verify live behavior from a detached process so the benchmark itself does not consume a server command slot.
