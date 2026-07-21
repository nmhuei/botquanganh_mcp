# Remediation Plan — Official Cycle 01

### REM-001 maps SEC-001
Implement quote-aware segmentation and regression tests.

### REM-002 maps SEC-002
Add a stable conflict code without exposing sensitive path data beyond existing behavior.

### REM-003 maps SEC-003
Separate HTTP transport success from command process exit success.

### REM-004 maps SEC-004
Record the dedicated metric at the exact rejection branch.

### REM-005 maps SEC-005
Protect shared limiter state with a lock and use monotonic time.

## Compatibility and rollback
All changes preserve public field names and configured limits. Each change can be reverted independently. Full-suite regression is required after any rollback.
