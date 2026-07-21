# Remediation Log — Official Cycle 01

- SEC-001: fixed with `_split_shell_chain`; old reproduction no longer returns `<parse-error>`.
- SEC-002: fixed with `FILE_EXISTS`; adapter regression passes.
- SEC-003: fixed; actual REST invocation of `false` returns HTTP 200 with exit code 1.
- SEC-004: fixed; 429 branch records exactly one hit in regression.
- SEC-005: fixed; 100 concurrent decisions allow exactly the configured 10 requests.

## Compatibility result
45 tests pass. Local/public transport configuration was not restarted or changed.

## Remaining risk
The shell parser is deliberately a bounded policy parser, not a complete Bash AST. Broader command-policy hardening is scheduled for Cycle 05.
