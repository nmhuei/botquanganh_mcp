# Implementation Plan — Official Cycle 07

## Goal
Provide complete HTTP observability and durable, redacted, versioned audit records.

## Tasks
1. Make metrics middleware outermost and finalize metrics on the final response body.
2. Track status/path counts, 4xx/5xx, auth failures, rate limits, in-flight/peak, average, p50, p95, and sample size.
3. Expose extended metrics through health while retaining compatibility fields.
4. Replace audit file handler with configured rotation.
5. Redact secret keys, inline credential formats, key material, and oversized strings.
6. Add schema version, event ID, service identity/version, UTC timestamp, and compact JSON.
7. Search active and rotated audit files with validated lookup IDs.
8. Add metric/middleware/audit tests and live public status-matrix verification.
