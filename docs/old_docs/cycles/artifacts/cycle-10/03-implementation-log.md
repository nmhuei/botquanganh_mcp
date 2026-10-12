# Implementation Log — Official Cycle 10

- Rebuilt `install.sh` around one canonical local/remote flow.
- Changed the remote default branch to `main`.
- Added branch existence validation, non-repository destination rejection, dirty-tree protection, tracked-branch checkout, and fast-forward-only updates.
- Added strict symlink target verification and clearer post-install validation steps.
- Kept `scripts/install_basic.sh` as a direct compatibility delegate.
- Added `scripts/manual_test_installer.sh` and wired its Bash syntax into the quality gate plus its execution into GitHub Actions.
- Fixed `scripts/restart_server_only.sh` to coordinate with the supervisor and inspect only TCP listener PIDs.
- Added `listening_pids_on_port` to shared process helpers and a connected-client regression test.
- Updated README installation/security guidance and release checklist.
- Removed unused imports/variables and normalized security suppressions.
- Regenerated final Ruff, Bandit, pip-audit, detect-secrets, ShellCheck, and zizmor results.
