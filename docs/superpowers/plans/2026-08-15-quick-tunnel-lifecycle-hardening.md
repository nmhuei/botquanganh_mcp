# Quick Tunnel Lifecycle Hardening

## Scope

- Preserve a live Quick Tunnel during code edits and normal FastMCP recovery.
- Make `bqa restart` and `bqa server restart` server-only.
- Disable automatic Quick Tunnel recreation in the supervisor.
- Reject stale connector URLs and add read-only failure diagnostics.
- Parse and publish URLs only from the current cold-start generation after readiness.
- Test lifecycle behavior with isolated fake processes; never exercise the live tunnel.

## Implementation checklist

- [x] Record live server, tunnel, supervisor PIDs, URL, process identity, timestamps, and logs.
- [x] Create a dedicated branch while preserving pre-existing local changes.
- [x] Trace lifecycle consumers and identify the stale whole-log URL parser.
- [x] Change the watchdog to server self-healing and tunnel monitor-only behavior.
- [x] Route both restart commands through `restart_server_only.sh`.
- [x] Preserve last-known URL as stale while refusing to advertise it as active.
- [x] Require current-generation URL, connector registration, local health, and public health before publication.
- [x] Add a read-only diagnostic chain for local health, DNS, public health, and MCP initialize.
- [x] Complete isolated regression tests; run the default non-live quality gate (its config-validation stage reports the pre-existing `MAX_CONCURRENT_COMMANDS=999999` failure).
- [x] Verify the original tunnel PID and URL are unchanged.

## Live-runtime invariant

The running supervisor was not restarted, so its loaded behavior remains the pre-patch
version until a future authorized cold start. This implementation must not stop, start,
restart, or signal the live supervisor or cloudflared process during verification.

## Authorized port migration

After the initial preservation work, the operator explicitly authorized replacing the
unused Quick Tunnel. The runtime was migrated from port `8000` to the BQA-specific
port `18427`; the old tunnel was intentionally retired and a new connector was
verified through local health, public health, and MCP initialize. Public-DNS fallback
is used when the host resolver retains a negative cache for a newly issued hostname.

## Script consumer audit

| Script | Classification | Canonical consumer/purpose |
|---|---|---|
| `run_mcp_tunnel.sh` | COMPATIBILITY WRAPPER | `app/cli/lifecycle.py`, operator compatibility |
| `scripts/start_tunnel_server.sh` | RUNTIME | cold start/supervisor backend |
| `scripts/stop_tunnel_server.sh` | RUNTIME | canonical destructive stop backend |
| `scripts/restart_server_only.sh` | RUNTIME | canonical restart backend |
| `scripts/process_helpers.sh` | RUNTIME | shared ownership/parser primitives |
| `scripts/collect_diagnostics.sh` | INSTALL/OPS | support bundle and quality gate |
| `scripts/dev.sh` | INSTALL/OPS | explicit developer entrypoint |
| `scripts/install_basic.sh` | COMPATIBILITY WRAPPER | installer compatibility and CI |
| `scripts/install_cli.sh` | INSTALL/OPS | CLI installation and quality gate |
| `scripts/uninstall_cli.sh` | INSTALL/OPS | CLI removal and quality gate |
| `scripts/manual_test_cli.sh` | TEST/CI | isolated CLI regression |
| `scripts/manual_test_installer.sh` | TEST/CI | installer regression and CI |
| `scripts/quality_gate.sh` | TEST/CI | canonical verification entrypoint |
| `scripts/test.sh` | COMPATIBILITY WRAPPER | documented quality-gate alias |
| `scripts/benchmark_resilience.py` | TEST/CI | explicit capacity benchmark entrypoint |
| `scripts/test_sse_client.py` | TEST/CI | explicit transport diagnostic entrypoint |
| `manual_test_tunnel_logic.sh` | TEST/CI | isolated fake-process lifecycle regression |
| `install.sh` | INSTALL/OPS | public installer entrypoint |
| `bin/bqa` | RUNTIME | installed CLI bootstrap wrapper |

No file qualifies for deletion: the only script without an in-repo caller,
`scripts/dev.sh`, remains an explicit developer/operator entrypoint. Reverse references
therefore remain intact and no compatibility surface was removed.
