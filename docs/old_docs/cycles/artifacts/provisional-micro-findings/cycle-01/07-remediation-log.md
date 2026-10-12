# Remediation Log — Cycle 01

### REM-001 / SEC-001
- Root cause: quote-unaware regex chain splitter.
- Fix applied: introduced `_split_shell_chain` state machine and reused it in command-name and recursive-rm inspection.
- Files changed: `app/host/policy.py`, `tests/test_host_tools.py`
- Test before fix: valid quoted command produced `<parse-error>` twice.
- Test after fix: command names equal `['python3']`.
- Security retest: PASS.
- Compatibility result: full suite PASS.
- Remaining risk: parser is intentionally limited and is not a complete Bash AST.
