# Remediation Plan — Cycle 01

### REM-001 maps SEC-001
- Priority: High
- Root cause: regex splitting occurs before shell quote parsing.
- Chosen fix: state-machine splitter tracking quote and escape state.
- Files/components: `app/host/policy.py`
- Compatibility impact: valid commands gain correct command identity; destructive blocking remains unchanged.
- Regression test: quoted separators and true chain.
- Security retest: reproduce old command and inspect names.
- Rollback: restore previous parser.
- Acceptance criteria: no `<parse-error>` for valid quoted command.
