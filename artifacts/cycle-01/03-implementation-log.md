# Implementation Log — Official Cycle 01

## TASK-001
- Added `_split_shell_chain`, a quote/escape-aware state machine.
- Reused it for command-name extraction and recursive-rm inspection.
- Added quoted separator and true-chain regressions.

## TASK-002
- Added explicit `FileExistsError → FILE_EXISTS` mapping and safe guidance.
- Added MCP adapter regression.

## TASK-003
- Updated REST status resolution so completed command envelopes with `exit_code` are HTTP 200.
- Added direct and full subprocess REST integration tests.

## TASK-004
- Added `metrics.record_rate_limit()` at the 429 rejection point.
- Added ASGI middleware regression.

## TASK-005
- Added an internal limiter lock.
- Made window cleanup/check/append atomic.
- Replaced wall-clock time with `time.monotonic()`.
- Added concurrent and clock-source tests.

## Deviations
An initial regression test missed an adapter import and was corrected before cycle completion. A malformed manual quote probe was discarded and replaced with a valid command plus automated tests.
