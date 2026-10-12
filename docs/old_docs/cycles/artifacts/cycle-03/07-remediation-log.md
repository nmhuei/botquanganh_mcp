# Remediation Log — Official Cycle 03

- All PID-based operations now require a matching managed command line.
- Stale/unrelated PIDs are removed from state files but their processes remain untouched.
- Server-only restart refuses unrelated port occupants.
- Stop script no longer executes broad `pkill` or blanket port kills.
- Supervisor hot path no longer performs dependency installation when the environment exists.
- Real restart preserved tunnel PID and URL while replacing only the server process.
