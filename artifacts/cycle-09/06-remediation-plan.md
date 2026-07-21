# Remediation Plan — Official Cycle 09

- REM-036: enforce mode 600 on `.env` during installation and validate it continuously.
- REM-037: validate every active setting, executable, storage path, and managed PID identity.
- REM-038: provide a diagnostics collector using redacted CLI outputs and excluding logs/secrets.
- REM-039: validate the transitive project dependency closure separately and report foreign packages as warnings.
- REM-040: add strict doctor/config modes and a single quality gate with runtime/full options.
- Document recovery, rollback, offline diagnosis, capacity, and production procedures.
