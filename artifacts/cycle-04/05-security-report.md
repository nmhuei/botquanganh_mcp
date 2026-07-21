# Security Report — Official Cycle 04

### SEC-012 — Directory listing disclosed symlink targets outside workspace
- Severity: High
- Confidence: Confirmed
- Category: Information exposure / path traversal
- CWE: CWE-200, CWE-59

### SEC-013 — Non-atomic file mutation and concurrent create race
- Severity: Medium
- Confidence: High
- Category: Integrity / race condition
- CWE: CWE-362

### SEC-014 — Append bypassed configured final file-size limit
- Severity: Medium
- Confidence: Confirmed
- Category: Resource exhaustion
- CWE: CWE-400

### SEC-015 — Replace loaded oversized files
- Severity: Medium
- Confidence: Confirmed
- Category: Resource exhaustion

### SEC-016 — Recursive search symlink traversal ambiguity
- Severity: Medium
- Confidence: High
- Category: Boundary enforcement

## Retest
All listed reproduction paths are blocked or bounded in unit and live REST tests.

## Residual risk
The implementation substantially narrows TOCTOU exposure using component rejection and final `O_NOFOLLOW`, but it is not a complete directory-FD/openat sandbox against a malicious same-user process replacing parent directories at exact race timing.

## Verdict
REMEDIATION_REQUIRED; findings fixed within the stated boundary model.
