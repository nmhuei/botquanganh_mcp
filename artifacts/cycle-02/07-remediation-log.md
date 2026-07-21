# Remediation Log — Official Cycle 02

- Installer creates and validates the global symlink.
- Uninstaller rejects unrelated targets with exit 1.
- Global invocation works from `/home/light` and isolated temporary directories.
- Invalid `bqa --json fs` returns a structured JSON error and exit code 2.
- All 48 tests pass.
