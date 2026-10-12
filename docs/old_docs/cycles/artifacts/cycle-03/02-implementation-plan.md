# Implementation Plan — Official Cycle 03

## Goal
Make process lifecycle ownership explicit and prevent accidental termination outside the repository.

### TASK-001 — Shared process ownership library
Add `/proc/<pid>/cmdline` validation for supervisor, server, and tunnel processes plus atomic runtime-file helpers.

### TASK-002 — Harden lifecycle scripts
Use ownership checks for adoption, status, stop, restart, and watchdog recovery. Refuse unrelated live PIDs. Remove broad `pkill` and unsafe port cleanup.

### TASK-003 — Remove installer from hot path
Run installation only when `.venv/bin/fastmcp` is missing.

### TASK-004 — Align Python CLI status
Require process identity, not just liveness, before reporting a component running.

### TASK-005 — Regression and real restart
Test unrelated PID refusal, matching process stop, isolated full lifecycle, and a real server-only restart preserving tunnel PID and URL.
