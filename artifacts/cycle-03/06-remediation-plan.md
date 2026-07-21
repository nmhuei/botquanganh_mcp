# Remediation Plan — Official Cycle 03

- REM-009: validate `/proc` command identity for every managed PID before use or termination.
- REM-010: stop only validated managed processes; report unrelated port occupants without touching them.
- REM-011: install dependencies only when required binaries are absent.
- Align shell and Python lifecycle status logic.
- Verify in isolated and live environments without restarting the public tunnel.
