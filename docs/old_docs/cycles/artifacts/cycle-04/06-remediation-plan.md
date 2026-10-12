# Remediation Plan — Official Cycle 04

- REM-012: lexical display plus `lstat` for entries; never resolve listed symlinks.
- REM-013: exclusive temporary files, fsync, atomic replace/hard-link, and file locking.
- REM-014: calculate and enforce final append size while holding an exclusive lock.
- REM-015: inspect source size before reading for replace.
- REM-016: reject symlink components and filter symlink directories/files in search.
- Retest through unit, concurrent, and public REST paths.
