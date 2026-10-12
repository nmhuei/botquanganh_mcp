# Implementation Plan — Official Cycle 08

## Goal
Bound process and client-state growth under concurrent load while retaining predictable API behavior.

## Tasks
1. Add configured command concurrency and queue timeout limits.
2. Add a thread-safe command capacity controller with active, queued, peak, started, and rejected telemetry.
3. Return stable `SERVICE_BUSY`/HTTP 503 when capacity cannot be obtained.
4. Replace rate-limit lists with bounded ordered deques and stale-client pruning.
5. Reject unseen clients conservatively when all tracked clients remain active.
6. Expose command and limiter capacity through health and capabilities.
7. Add deterministic concurrency/capacity tests.
8. Create a reusable non-destructive benchmark script and run detached live load tests.
