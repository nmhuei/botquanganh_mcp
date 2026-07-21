# Security Report — Official Cycle 06

### SEC-022 — Public error contract inconsistency
- Severity: Medium
- Confidence: Confirmed
- Impact: clients could mis-handle failures and retry unsafe operations.

### SEC-023 — Internal exception detail exposure
- Severity: High
- Confidence: Confirmed
- Category: Information exposure
- CWE: CWE-209

### SEC-024 — Absolute host path exposure
- Severity: Medium
- Confidence: Confirmed
- Category: Information exposure

### SEC-025 — Plaintext auth and non-standard rate-limit errors
- Severity: Medium
- Confidence: Confirmed
- Category: API contract/security controls

### SEC-026 — OpenAPI did not reflect actual error behavior
- Severity: Low
- Confidence: Confirmed
- Category: Contract/documentation

## Retest
Exception matrix, auth, rate-limit, REST negative paths, redaction, and public OpenAPI checks passed.

## Verdict
REMEDIATION_REQUIRED; findings fixed in scope.
