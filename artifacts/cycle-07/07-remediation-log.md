# Remediation Log — Official Cycle 07

- HTTP metrics now include every completed request, including rejected authentication and rate-limit responses.
- Final-body timing replaces response-start timing.
- Health exposes extended counters and percentiles.
- Audit storage rotates at configured size and keeps bounded backups.
- Inline credentials, assignments, API-key shapes, and key blocks are redacted.
- Audit events are compact, versioned, uniquely identified, and searchable across rotations.
- Live metrics and audit schema checks passed with tunnel preserved.
