# Security Report — Official Cycle 05

## Findings

### SEC-017 — Host command inherited server credentials
- Severity: High
- Confidence: Confirmed
- Category: Information exposure
- Impact: commands could read gateway or API credentials from the server process environment.

### SEC-018 — Shell startup environment injection
- Severity: High
- Confidence: High
- Category: Command execution integrity
- Impact: startup variables or login profiles could run unintended code.

### SEC-019 — Unbounded command capture before truncation
- Severity: High
- Confidence: Confirmed
- Category: Resource exhaustion
- Impact: output could consume unbounded temporary storage before the response was truncated.

### SEC-020 — Dynamic shell construct bypass in allowlist mode
- Severity: High
- Confidence: High
- Category: Policy bypass

### SEC-021 — Background-chain audit omission
- Severity: Medium
- Confidence: Confirmed
- Category: Audit and policy correctness

## Retest
Credential redaction, startup-hook suppression, output bounds, process-group cleanup, and policy regressions passed.

## Residual risk
`guarded` remains a destructive-operation guard rather than a sandbox. Strong isolation requires a separate container or sandbox boundary.

## Verdict
REMEDIATION_REQUIRED; findings fixed within the documented guarded-policy model.
