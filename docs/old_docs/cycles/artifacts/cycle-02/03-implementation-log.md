# Implementation Log — Official Cycle 02

- Added `CLIArgumentParser` to route usage errors through `CLIError`.
- Added `scripts/install_cli.sh` with configurable target directory and post-install verification.
- Added `scripts/uninstall_cli.sh` with ownership verification before removal.
- Integrated global CLI installation into `scripts/install_basic.sh`.
- Kept `bin/bqa` symlink-safe using resolved source location.
- Added subprocess-level integration tests for installation, removal, external cwd, and JSON usage errors.
