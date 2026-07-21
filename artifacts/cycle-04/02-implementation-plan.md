# Implementation Plan — Official Cycle 04

## Goal
Make public host filesystem operations bounded, atomic, symlink-resistant, and concurrency-safe.

### TASK-001 — Path validation hardening
Perform lexical and resolved workspace checks, reject symlink components by default, and use `O_NOFOLLOW` for final file opens.

### TASK-002 — Safe directory listing/search
Use `lstat`, never follow symlink targets for metadata/path display, and exclude symlink directories from recursive search.

### TASK-003 — Atomic writes
Write to an exclusive temporary file, fsync, preserve mode, and atomically replace or hard-link for no-overwrite semantics.

### TASK-004 — Bounded append/replace
Lock appends, validate final size, serialize writes, enforce source-file size during replace, and fsync successful mutations.

### TASK-005 — Adversarial and concurrency tests
Cover external symlinks, target leakage, search traversal, concurrent create, concurrent append, oversize append/replace, and mode preservation.

### TASK-006 — Public runtime verification
Reload only the bridge, preserve tunnel PID/URL, and repeat symlink tests through `bqa`/REST.
