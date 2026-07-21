# Security Report — Official Cycle 02

### SEC-006 — Unowned global CLI path could be removed unsafely
- Severity: Medium
- Confidence: High
- Category: Installer safety
- Mitigation: uninstaller resolves the target and refuses anything not owned by this repository.

### SEC-007 — CLI usage errors bypassed structured error contract
- Severity: Low
- Confidence: Confirmed
- Category: Interface reliability
- Impact: automation could receive non-JSON output despite requesting JSON.

### SEC-008 — Symlink-relative bootstrap failure
- Severity: Medium
- Confidence: Confirmed
- Category: Packaging/reliability
- Impact: global invocation failed outside the repository.

No token values were printed by installer tests. No external scanner was available.

## Verdict
REMEDIATION_REQUIRED; listed findings fixed in this cycle.
