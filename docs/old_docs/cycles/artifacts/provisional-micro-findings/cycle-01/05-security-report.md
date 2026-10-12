# Security Report — Cycle 01

## Scope
Source review and local non-destructive tests of command policy parsing.

### SEC-001 — Quoted shell separators corrupt command identity
- Severity: Medium
- Confidence: Confirmed
- Category: Audit/policy parsing
- CWE: CWE-20
- Affected component: `app/host/policy.py`
- Reachability: Any `host_check_command` or `host_run_command` request containing quoted separators.
- Evidence: valid Python command returned two `<parse-error>` names.
- Impact: inaccurate audit data and false allowlist rejection.
- Recommended remediation: quote-aware chain splitting and regression tests.
- Regression test: added.

## Scanner limitations
No SAST/SCA scanner was installed. CVE status was not asserted.

## Verdict
REMEDIATION_REQUIRED
