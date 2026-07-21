# Remediation Plan — Official Cycle 10

- REM-041: align the one-line installer and clone target on `main`; validate remote branches before mutation.
- REM-042: update managed clones only through clean working trees and fast-forward merges.
- REM-043: verify `.env` preservation/mode, symlink ownership, CLI execution, and dependency consistency in isolated installs.
- REM-044: distinguish listening server processes from connected clients and coordinate restart ownership with the supervisor.
- REM-045: add regression coverage for both installer customer flows and connected-client port inspection.
- REM-046: maintain clean static/security scan evidence and include installer regression in CI/release documentation.
- REM-047: preserve the live tunnel during server-only recovery and final validation.
