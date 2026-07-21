# Remediation Plan — Official Cycle 05

- REM-017: remove credential-like inherited variables by default; retain only explicit allowlist exceptions.
- REM-018: strip execution-control variables and disable shell startup profiles.
- REM-019: drain stdout/stderr continuously while retaining only bounded bytes.
- REM-020: reject dynamic shell constructs in allowlist mode.
- REM-021: treat single ampersand as a chain boundary for command identity.
- Retest process descendants, dual-stream output, live environment behavior, and public transport.
