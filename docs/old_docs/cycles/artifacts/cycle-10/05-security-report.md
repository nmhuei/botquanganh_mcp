# Security Report — Official Cycle 10

### SEC-041 — Remote installer branch mismatch and stale update behavior
- Severity: Medium
- Confidence: Confirmed
- Impact: customers could download the installer from `main` but receive a different branch, while reruns could leave an old working tree installed.
- Resolution: default to `main`, validate the branch, and apply fast-forward-only updates.

### SEC-042 — Existing installer could overwrite an operator-managed directory
- Severity: Medium
- Confidence: Confirmed
- Impact: ambiguous destinations or local changes could be altered during update.
- Resolution: reject non-Git destinations and dirty working trees.

### SEC-043 — Server-only restart misclassified the tunnel client as a port owner
- Severity: Medium
- Confidence: Confirmed
- Impact: bridge recovery failed while the tunnel remained connected, and supervisor/restart races could create repeated server processes.
- Resolution: inspect TCP listeners only and delegate recreation to the active supervisor.

### SEC-044 — Static-analysis noise obscured the final release signal
- Severity: Low
- Confidence: Confirmed
- Impact: unused code and false positives made release triage less reliable.
- Resolution: remove unused code, narrow suppressions, and regenerate clean final scans.

## Retest

All findings passed focused and full regression tests. Final SAST, dependency, secret, shell, and workflow scans report zero findings.

## Residual risk

The active development environment has authentication disabled by operator choice. The shipped `.env.example` requires authentication; customer/public use must set a fresh gateway token.
