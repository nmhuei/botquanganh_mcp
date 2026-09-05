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

### Server hangs mid-response: undrained `stderr=subprocess.PIPE`

If the MCP server is launched by a wrapper that captures its stderr with
`subprocess.PIPE` and never drains it, the pipe's fixed buffer eventually fills
and every write to stderr blocks — the server deadlocks mid-response while a
request is in flight. Capture stderr to a file (or a `tempfile`) instead of an
undrained pipe. This applies to supervisors, tunnel runners, and any test
harness that spawns the server.

Two-line reproduction hint: spawn the server with
`subprocess.Popen(..., stderr=subprocess.PIPE)` and never call `.read()`/`.communicate()`; once enough log volume accumulates
(e.g. hammer it with `scripts/stress_mcp.py`), requests stop completing even
though the process is alive.

Check for this first when the symptom is "server alive but all requests hang":

```bash
ls -l /proc/<server-pid>/fd | grep pipe
```

combined with a wrapper that is not reading from its end of the pipe.

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

### Liveness checks under load

Use `/healthz` when checking whether the server is alive under load: it bypasses
the REST blocking pool and always answers, even during command storms. Cheap
in-memory REST handlers such as health, capabilities, and jobs also use the
non-blocking fast path. Filesystem, command, log-tail, and activity requests
that touch disk or other blocking resources continue to use the shared
16-slot limiter so expensive work remains bounded.

Audit logs rotate according to:

```env
AUDIT_LOG_MAX_BYTES=10000000
AUDIT_LOG_BACKUP_COUNT=5
```

## 9. Quan sát & dọn dẹp

### Watch every log from one place

`bqa logs all` merges server, tunnel, launcher, and audit output into a single
view, prefixing each line with its `[source]` tag. The shared filters work on
the merged view; `-f` follows all sources at once.

```bash
bqa logs all -n 200                  # last 200 merged lines
bqa logs all --since 10m             # entries newer than ten minutes
bqa logs all --grep error            # only lines containing "error"
bqa logs all -f --grep Traceback     # follow all sources, filtered live
bqa logs all --json                  # machine-readable snapshot (--quiet drops headers)
```

The same snapshot is available over REST without following:

```bash
curl -s "http://127.0.0.1:18427/api/v1/logs/tail?lines=100&grep=error"
```

Query parameters: `sources` (comma-separated stream names; defaults to all),
`lines` (capped at 500), `grep`. The endpoint is stateless — one snapshot per
request, no follow mode.

### Lifecycle sweeper for chat workspaces

Plan first, apply deliberately. Without `--apply` the sweeper is a dry run:

```bash
python -m app.chat_sweeper           # dry-run: prints planned actions only
python -m app.chat_sweeper --apply   # archive/delete for real
./scripts/sweep_chat_workspaces.sh   # shell wrapper around the same sweep
```

Automation: the managed supervisor triggers the sweep once per hour
(`HOST_CHAT_SWEEP_INTERVAL_MINUTES`, default `60`) and the gate only fires when
chat workspaces are enabled (`HOST_CHAT_WORKSPACES=true`). Sweeps run by the
supervisor stay dry-run unless `HOST_CHAT_SWEEP_APPLY=true`.

The sweep acts in order: delete archived workspaces past retention, archive
idle ones, then enforce workspace count and root footprint thresholds.

### Where the underlying files live

You rarely need these directly — `bqa logs all` and `/api/v1/logs/tail`
aggregate everything below.

| File | Content |
| --- | --- |
| `logs/server.log` | MCP bridge/server runtime output |
| `logs/cloudflared.log` | Quick Tunnel process output |
| `logs/launcher.log` | Desktop UI / background launcher output |
| `logs/gateway.log` | Rotating audit trail (`AUDIT_LOG_*` controls rotation) |
| `<HOST_CHAT_ROOT>/<chat_id>/journal.jsonl` | Per-chat activity journal |
| `<HOST_CHAT_ROOT>/.archive/<chat_id>/` | Archived workspaces awaiting retention deletion |

## 10. Production checklist

Before deployment:

1. Set `REQUIRE_AUTH=true`.
2. Generate and configure a fresh gateway token.
3. Keep `.env` mode `600`.
4. Run `bqa config validate --strict`.
5. Run `./scripts/quality_gate.sh --full` against the authorized target.
6. Confirm no uncommitted or unreviewed changes.
7. Confirm request-rate limits and host resources are appropriate for expected parallel load.
8. Record rollback and recovery commands.


### Live workspace journal stream

For per-chat structured operation logs, prefer `/api/v1/activity/stream` over repeatedly tailing `journal.jsonl` by hand. The endpoint is an SSE stream with bounded replay, `Last-Event-ID` resume, reconnect hints, heartbeat comments, and the same workspace classification filters as `/api/v1/activity`.

```bash
curl -N \
  -H 'Accept: text/event-stream' \
  'http://127.0.0.1:18427/api/v1/activity/stream?severity=ERROR&replay=50'
```

If a reverse proxy is introduced, verify that it does not buffer `text/event-stream`; the application sends `X-Accel-Buffering: no` and `Cache-Control: no-cache, no-transform`. The BQA desktop Control Center reconnects automatically and resumes from the last event id.
