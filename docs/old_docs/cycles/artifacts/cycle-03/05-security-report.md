# Security Report — Official Cycle 03

### SEC-009 — PID reuse could terminate unrelated processes
- Severity: High
- Confidence: High
- Category: Process lifecycle / availability
- CWE: CWE-415-like lifecycle ownership error
- Impact: stop/restart could terminate another user process if a stale PID was reused.

### SEC-010 — Broad port and process cleanup
- Severity: High
- Confidence: Confirmed
- Category: Availability
- Impact: `lsof`/`pkill` cleanup could terminate processes not started by this repository.

### SEC-011 — Runtime startup mutates dependencies
- Severity: Medium
- Confidence: Confirmed
- Category: Supply-chain/reliability
- Impact: each lifecycle start could upgrade/install packages unexpectedly.

## Retest
Ownership checks and unrelated-process refusal passed. Broad kill paths were removed.

## Verdict
REMEDIATION_REQUIRED; findings fixed in scope.
