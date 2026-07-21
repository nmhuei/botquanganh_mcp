# Implementation Log — Official Cycle 03

- Added `scripts/process_helpers.sh` with PID validation, command-line matching, atomic writes, and safe managed stop.
- Updated `run_mcp_tunnel.sh`, `start_tunnel_server.sh`, `restart_server_only.sh`, and `stop_tunnel_server.sh`.
- Removed unconditional installation during supervisor startup.
- Removed broad `pkill` and unrelated port termination.
- Updated `app/cli/lifecycle.py` to match process identity via `/proc`.
- Added process-helper tests and updated lifecycle tests.
- Updated isolated regression bundle to include the helper and preserve fake process identity.
