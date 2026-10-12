# Remediation Plan — Official Cycle 07

- REM-027: move metrics outside auth/rate limiting and count final response status once.
- REM-028: add distribution, percentile, and concurrency measurements.
- REM-029: use bounded rotating audit files with configurable backup count.
- REM-030: redact both sensitive keys and credential-shaped string content; cap fields.
- REM-031: version and uniquely identify every audit event.
- Verify through unit middleware tests and live public status requests.
