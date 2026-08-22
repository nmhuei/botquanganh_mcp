# Host MCP Architecture

## Runtime flow

```text
ChatGPT / bqa / REST client
        │
        ├── local HTTP
        └── Cloudflare Tunnel (optional)
                 │
                 ▼
       MetricsMiddleware (outermost)
                 │
                 ▼
       TokenAuthMiddleware
       └── gateway-token verification
                 │
                 ▼
       FastMCP + Starlette application
       ├── /healthz
       ├── /mcp
       │     └── MCP adapters
       └── /api/v1
             └── REST adapters
                 │
                 ▼
       Shared host services
       ├── paths.py       lexical/resolved workspace policy
       ├── files.py       no-follow, atomic, bounded filesystem operations
       ├── policy.py      command identity and guarded/allowlist policy
       ├── executor.py    sanitized, bounded, capacity-controlled processes
       └── inventory.py   guide/tool inventory and trusted version probes
```

## Dependency rules

- `app/host/` contains reusable host business logic and no MCP decorators or HTTP routes.
- `app/tools/` adapts MCP calls to the host services.
- `app/rest_api.py` adapts REST calls to the same host services.
- `app/error_contract.py` is the shared public error/status/OpenAPI taxonomy.
- `app/cli/` calls REST for host operations and wraps repository-owned lifecycle scripts for local process operations.
- `knowledge/` contains documents and declarative tool metadata, not executable code.
- Tool registration in `app/main.py` is explicit.

## Tool surface

The server exposes exactly 12 MCP tools:

```text
health_check
get_capabilities
host_list_directory
host_read_file
host_write_file
host_replace_in_file
host_append_file
host_make_directory
host_search_text
host_check_command
host_run_command
host_knowledge
```

## Command execution flow

`host_run_command`:

1. Acquires one bounded command-capacity slot.
2. Validates timeout and command policy.
3. Resolves `cwd` inside the workspace boundary.
4. Builds a sanitized child environment.
5. Starts an absolute Bash executable with `--noprofile --norc -c`.
6. Drains stdout and stderr concurrently while retaining bounded bytes.
7. Terminates the full process group on timeout.
8. Returns the child exit code independently from HTTP transport success.
9. Records a command hash, command identities, timing, truncation, and exit metadata.
10. Releases capacity in every success/error path.

Overload behavior is deterministic: callers that cannot acquire capacity within `COMMAND_QUEUE_TIMEOUT_SECONDS` receive `SERVICE_BUSY` with HTTP 503.

## Filesystem flow

Public file operations:

1. Normalize the lexical path without following symlinks.
2. Check the lexical workspace boundary.
3. Reject existing symlink components.
4. Resolve and check the final workspace boundary.
5. Open the final component with no-follow semantics where supported.
6. Require a regular file for file operations.
7. Enforce byte limits.
8. Use locking and atomic/fsynced mutation where applicable.

Listings and search use lexical display paths and do not expose or traverse symlink targets.

## Error contract

MCP, REST, middleware, CLI HTTP handling, and OpenAPI share these public codes:

```text
INVALID_ARGUMENT
AUTH_REQUIRED
POLICY_BLOCKED
FILE_NOT_FOUND
TIMEOUT
FILE_EXISTS
RATE_LIMITED
SERVICE_BUSY
INTERNAL_ERROR
```

Unexpected internal exceptions return a generic public message. Known repository, workspace, and home paths are redacted from expected public errors.

## Metrics and audit

Metrics are recorded after the final HTTP response body and include authentication rejections. Health exposes status/path counts, client/server errors, auth failure counts, average/p50/p95 latency, in-flight/peak requests, and command capacity.

Audit events are versioned JSONL records written to a rotating log. Sensitive keys, inline credential formats, and key material are redacted; long fields are truncated.

## Lifecycle architecture

```text
run_mcp_tunnel.sh
        │
        ▼
start_tunnel_server.sh supervisor
        ├── FastMCP server process
        └── cloudflared Quick Tunnel process
```

- Server and tunnel start independently.
- The canonical tunnel URL is written atomically to `logs/tunnel_url.txt`.
- Process ownership is validated through `/proc/<pid>/cmdline`, not PID liveness alone.
- The supervisor self-heals a failed or unhealthy FastMCP server.
- The tunnel is monitor-only: tunnel loss is logged and never triggers automatic cloudflared recreation.
- The last-known URL remains available for diagnostics with `url_state=stale`, but `bqa url` refuses it.
- `bqa restart` and `bqa server restart` converge on one server-only implementation and preserve tunnel PID/URL.
- Cold start parses only cloudflared log bytes written by the current launch and publishes the URL only after local health, connector registration, and public health succeed.
- Stop operations terminate the ownership controller first and refuse unrelated reused PIDs.

## CLI and operations

`bqa` has two execution modes:

- local lifecycle operations through repository scripts;
- host operations through the REST API using local, public, or explicit base URLs.

The bootstrap wrapper resolves its real path, so the global symlink works from any directory. `scripts/install_cli.sh` and `scripts/uninstall_cli.sh` manage only the repository-owned symlink.

`./scripts/quality_gate.sh` is the canonical source/runtime/full verification entry point. `scripts/collect_diagnostics.sh` creates a redacted support bundle.

## Knowledge flow

`host_knowledge` reads Markdown guides and `TOOL_CATALOG.json`, checks executable availability from `PATH`, and runs only catalog-declared version arguments against resolved executable paths. Callers cannot supply arbitrary version-probe commands.
