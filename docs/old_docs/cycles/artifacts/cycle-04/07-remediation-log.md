# Remediation Log — Official Cycle 04

- External symlink targets are no longer exposed in listings.
- Direct reads/writes/replaces/appends reject symlink paths and use no-follow final opens.
- Writes are atomic and preserve existing mode.
- No-overwrite creation is atomic under concurrent callers.
- Append operations are serialized and cannot exceed final configured size.
- Replace refuses oversized source files before loading them.
- Search excludes symlink directories and non-regular files.
- Live public retest passed after server-only reload.
