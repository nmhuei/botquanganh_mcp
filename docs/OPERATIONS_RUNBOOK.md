# Operations Runbook

## 1. Installation

```bash
cd /home/light/GitHub/botquanganh_mcp
./scripts/install_basic.sh
```

The installer:

- creates or reuses `.venv`;
- installs pinned runtime dependencies;
- installs the editable `bqa` package;
- creates the global `~/.local/bin/bqa` symlink;
- creates `.env` when absent;
- applies mode `600` to `.env`;
- restores executable bits on CLI and shell scripts.

Verify:

```bash
bqa version
bqa config validate
```

## 2. Normal lifecycle

Start or adopt the managed supervisor:

```bash
bqa start
```

Inspect status:

```bash
bqa status
bqa doctor
```

After ordinary Python/code changes, restart only the bridge:

```bash
bqa restart
```

`bqa restart` and `bqa server restart` use the same server-only implementation and
must preserve the tunnel PID and URL.

Do not use `stop && start` as MCP recovery. `bqa stop` is an intentional destructive
shutdown: stopping `cloudflared` invalidates the random Quick Tunnel hostname.

```bash
bqa status
./scripts/diagnose_tunnel.sh
```

If the tunnel dies, the supervisor keeps FastMCP healthy but does not recreate the
tunnel. Provision a new Quick Tunnel only through an explicit cold `bqa start` after
the old supervisor state has been intentionally retired during an authorized window.

## 3. Quality gates

Source and configuration gate:

```bash
./scripts/quality_gate.sh
```

Include local runtime checks:

```bash
./scripts/quality_gate.sh --runtime
```

Include public runtime and isolated lifecycle regression:

```bash
./scripts/quality_gate.sh --full
```

The legacy command remains an alias:

```bash
./scripts/test.sh
```

## 4. Doctor modes

Normal doctor allows warnings:

```bash
bqa doctor
```

Offline/local-only diagnosis:

```bash
bqa doctor --local-only
```

Strict production-style diagnosis treats warnings as failures:

```bash
bqa doctor --strict
bqa config validate --strict
```

`REQUIRE_AUTH=false` intentionally produces a warning. It is acceptable for the current development setup and should be enabled before production deployment.

## 5. Diagnostics collection

Create a redacted diagnostics directory:

```bash
./scripts/collect_diagnostics.sh
```

Choose a destination:

```bash
./scripts/collect_diagnostics.sh artifacts/support-case-001
```

The bundle excludes `.env` contents and runtime log bodies. It contains redacted configuration, status, doctor output, package metadata, and Git identity/state.

## 6. Recovery procedures

### Bridge is down but tunnel is alive

```bash
bqa status
bqa server restart
bqa health
bqa --public health
```

Confirm tunnel PID and URL remain unchanged.

### Stale PID file

Run:

```bash
bqa config validate
bqa doctor --local-only
```

Lifecycle scripts validate `/proc/<pid>/cmdline` before stopping a process. Unrelated reused PIDs are not terminated. Starting the supervisor removes/replaces stale managed state safely.

### Tunnel process is dead

```bash
bqa status
bqa start
```

The supervisor should recreate only the tunnel and publish the fresh canonical URL in `logs/tunnel_url.txt`.

### Port 18427 is occupied by an unrelated process

`bqa server restart` refuses to terminate it. Identify the process manually:

```bash
lsof -nP -i :18427
```

Resolve the conflict explicitly; do not bypass the ownership check.

### Global `bqa` command is missing

```bash
./scripts/install_cli.sh
rehash   # zsh
bqa version
```

Remove only the repository-owned symlink:

```bash
./scripts/uninstall_cli.sh
```

## 7. Rollback

Before rollback, collect diagnostics and record the current tree:

```bash
./scripts/collect_diagnostics.sh artifacts/pre-rollback

git status --short
git diff --check
```

Restore only the intended files or commit. Do not reset unrelated user changes. After rollback:

```bash
./scripts/quality_gate.sh
bqa server restart
bqa doctor
```

A rollback of normal code must not restart the tunnel.

## 8. Logs and request controls

```bash
bqa logs server -n 100
bqa logs tunnel -n 100
bqa logs audit -n 100
bqa health --json
```

Health exposes:

- request/error/status counts;
- p50/p95 latency;
- in-flight and peak requests;
- tracked rate-limit clients and capacity rejections.

Audit logs rotate according to:

```env
AUDIT_LOG_MAX_BYTES=10000000
AUDIT_LOG_BACKUP_COUNT=5
```

## 9. Production checklist

Before deployment:

1. Set `REQUIRE_AUTH=true`.
2. Generate and configure a fresh gateway token.
3. Keep `.env` mode `600`.
4. Run `bqa config validate --strict`.
5. Run `./scripts/quality_gate.sh --full` against the authorized target.
6. Confirm no uncommitted or unreviewed changes.
7. Confirm request-rate limits and host resources are appropriate for expected parallel load.
8. Record rollback and recovery commands.
