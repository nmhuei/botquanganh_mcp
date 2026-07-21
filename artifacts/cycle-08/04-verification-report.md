# Verification Report — Official Cycle 08

## Automated verification
- Focused resilience tests: 25 passed.
- Full suite: 93 passed.
- compileall, Bash syntax, and diff check: PASS.

## Capacity verification
- Configured maximum concurrent commands: 4.
- Detached live load: 8 simultaneous three-second commands produced exactly 4 HTTP 200 and 4 HTTP 503 `SERVICE_BUSY` responses.
- Total command batch duration: 3095.7 ms, confirming no serial eight-command execution and no oversubscription.
- Health telemetry reported peak active 4, queue 0 after completion, and capacity rejections.
- Rate-limiter tests confirmed bounded client state, conservative rejection, stale pruning, and retained active quotas.

## Final benchmark
40 health requests, 10 workers:
- Local: 1237.9 requests/s, p50 6.1 ms, p95 10.7 ms, maximum 11.9 ms.
- Public: 24.6 requests/s, p50 240.3 ms, p95 877.0 ms, maximum 878.0 ms.

The local service remained fast; public latency remained external-path dominated.

## Runtime
- Server PID changed to 172005.
- Tunnel PID 65323 and canonical URL remained unchanged.
- Public health final gate: PASS.

## Verdict
PASS
