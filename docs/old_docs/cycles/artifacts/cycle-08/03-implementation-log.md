# Implementation Log — Official Cycle 08

- Added `MAX_CONCURRENT_COMMANDS`, `COMMAND_QUEUE_TIMEOUT_SECONDS`, and `RATE_LIMIT_MAX_CLIENTS` configuration.
- Added `SERVICE_BUSY` to the shared error taxonomy and OpenAPI response matrix.
- Added `CommandCapacity` around all host command execution.
- Reworked the rate limiter with `OrderedDict` plus `deque`, stale-state pruning, bounded client capacity, and operational counters.
- Exposed command/limiter capacity in health and configured limits in capabilities.
- Added `tests/test_resilience_capacity.py` and extended error-contract coverage.
- Added reusable `scripts/benchmark_resilience.py`.
- Reloaded only the bridge and ran detached live command/health benchmarks.
