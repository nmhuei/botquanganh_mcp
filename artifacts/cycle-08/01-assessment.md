# Repository Assessment — Official Cycle 08

## Executive summary
The local host service was fast, while public latency was dominated by the Cloudflare/connector path. However, repository resource controls still allowed unbounded command-process concurrency and unbounded per-client rate-limit state. Under load, these could exhaust processes, memory, file descriptors, or host CPU even when individual command output and duration were bounded.

## Baseline benchmark
40 health requests with 10 workers:
- Local: p50 4.7 ms, p95 14.8 ms, maximum 16.1 ms.
- Public: p50 219.3 ms, p95 885.2 ms, maximum 1024.0 ms.

## Main risks
1. Every concurrent command request could spawn a new process.
2. No queue timeout or service-busy contract existed.
3. Rate-limit client keys could grow without a configured maximum.
4. List-based sliding windows required repeated list allocation and linear filtering.
5. Evicting active limiter state would reset quotas, so capacity behavior needed to be conservative.
6. Resource-capacity state was not visible in health/capabilities.
