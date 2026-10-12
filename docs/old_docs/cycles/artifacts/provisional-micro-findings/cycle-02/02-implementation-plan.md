# Implementation Plan — Cycle 02

## TASK-001 — Stable file conflict error
- Change `format_error_response` to map `FileExistsError` to `FILE_EXISTS`.
- Add a public adapter regression test.
- Preserve REST HTTP 409 behavior.
- Done when full suite passes and the MCP envelope reports `FILE_EXISTS`.
