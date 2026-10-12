# Remediation Log — Official Cycle 08

- Command execution now has a configured maximum and bounded queue wait.
- Capacity is always released after validation errors, command completion, and timeout paths.
- Overload returns JSON `SERVICE_BUSY` with HTTP 503 rather than spawning another process.
- Rate-limit state is bounded by client count and uses efficient deque expiry.
- Active client quotas are not silently evicted.
- Health and capabilities expose current and configured resource capacity.
- Detached live benchmark confirmed exactly four active command slots and four overload rejections.
