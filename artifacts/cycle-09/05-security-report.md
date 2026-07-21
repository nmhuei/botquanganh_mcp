# Security Report — Official Cycle 09

### SEC-036 — Credential file readable by group/other users
- Severity: High
- Confidence: Confirmed
- Category: Secret storage permissions
- Impact: `.env` mode 664 allowed broader local read access than required.

### SEC-037 — Incomplete operational configuration validation
- Severity: Medium
- Confidence: Confirmed
- Impact: invalid capacity, audit, boolean, path, or process settings could reach runtime unnoticed.

### SEC-038 — Diagnostics process could encourage unsafe manual data collection
- Severity: Medium
- Confidence: High
- Category: Information exposure
- Impact: operators lacked a standard bundle excluding secrets and log payloads.

### SEC-039 — Dependency gate mixed project and unrelated tool conflicts
- Severity: Medium
- Confidence: Confirmed
- Category: Supply-chain operations
- Impact: a noisy gate could be ignored entirely, hiding real project dependency breakage.

### SEC-040 — No strict production-oriented readiness mode
- Severity: Medium
- Confidence: Confirmed
- Impact: accepted development warnings could be mistaken for production readiness.

## Retest
File mode, complete config checks, strict/local doctor, project closure, diagnostics exclusions, and quality gate all passed.

## Residual risk
The current virtualenv contains 188 unrelated packages and two full-environment dependency conflicts. The project dependency closure is consistent, but production should use a freshly rebuilt dedicated virtualenv. Authentication remains intentionally disabled for development.

## Verdict
REMEDIATION_REQUIRED; primary findings fixed, residual environment hygiene explicitly reported.
