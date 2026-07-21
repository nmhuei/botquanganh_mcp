# Remediation Plan — Cycle 02

### REM-002 maps SEC-002
- Root cause: `FileExistsError` fell through generic exception mapping.
- Fix: add stable `FILE_EXISTS` code and non-sensitive guidance.
- Regression: call public host-write adapter with overwrite disabled.
