# Implementation Plan — Official Cycle 02

## Goal
Turn `bqa` into a reliably installable CLI with stable invocation and error contracts.

### TASK-001 — Parser error contract
- Replace argparse termination on errors with `CLIError(EXIT_USAGE)`.
- Preserve normal `--help` and `--version` behavior.
- Verify `--json` usage errors are JSON on stderr.

### TASK-002 — Global installer
- Add idempotent `scripts/install_cli.sh`.
- Install a symlink into `${BQA_BIN_DIR:-$HOME/.local/bin}`.
- Resolve and execute the installed command before reporting success.

### TASK-003 — Safe uninstaller
- Remove only a symlink resolving to this repository's wrapper.
- Refuse unrelated files or symlinks.

### TASK-004 — Bootstrap integration
- Call installer from `install_basic.sh` after editable package installation.
- Keep `.venv/bin/bqa` and repository wrapper operational.

### TASK-005 — Subprocess contract matrix
Test external cwd, global symlink, install/uninstall, unrelated-target refusal, JSON usage errors, and existing command matrix.
