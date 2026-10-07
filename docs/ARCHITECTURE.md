# BQA MCP 2.0 Architecture

## Runtime flow

```text
ChatGPT / bqa / REST client
        |
        +-- local HTTP
        +-- Cloudflare Tunnel
                |
                v
FastMCP + Starlette
        |
        +-- /healthz
        +-- /mcp
        +-- /api/v1
                |
                v
Shared host services and chat workspaces
```

`app/host/` contains shared host logic. `app/tools/` adapts MCP requests.
`app/rest_api.py` adapts REST requests. `app/cli/` calls REST and lifecycle scripts.

## MCP tool surface

The server exposes eight super-tools.

| Tool | Responsibility |
| --- | --- |
| `server_info` | Return health, limits, sandbox path and tool catalog. |
| `workspace_context` | Bind and resume workspaces. Persist state, notes and hypotheses. |
| `workspace_explore` | List directories and read bounded file windows. |
| `workspace_edit` | Write, append and replace text with validation. |
| `workspace_search` | Search file content and paths with bounded results. Returns partial results with `limit_reason` on deadline, work, scan, cap, queue, or payload budgets. |
| `terminal_execute` | Run shell commands with adaptive task detachment. |
| `task` | Manage detached task processes and their output. |
| `web_intelligence` | Fetch and parse bounded HTTP or HTTPS content. |

Call `workspace_context(action="bind")` before workspace operations when
`ATTRIBUTION_MODE=enforce`. `server_info` and `workspace_context` are exempt
from this binding requirement.

## Process execution

`terminal_execute` runs synchronously by default. It returns a task identifier
when the caller sets `background=true`. It can also detach when the caller
sets a non-default `wait_ms_before_async` value, leaves `timeout_seconds`
unset, and does not set `background=false`. The `task` tool can wait, tail
output, report status, list tasks, send input, or terminate a task process
group.

The task manager drains standard output and error concurrently. It stores
logs under `~/Downloads/bqa-trash/task-logs` and applies configured task
quotas. The `task` tool bounds returned tail output.

The shared REST command executor invokes Bash with `--noprofile --norc`.
`terminal_execute` invokes `/bin/bash -lc`, so login shell profiles can affect
that MCP tool. When REST command capacity is full, the service returns
`SERVICE_BUSY` with HTTP status 503.

## Workspace operations

`workspace_explore`, `workspace_edit` and `workspace_search` resolve paths
inside configured scopes. They journal attributable workspace operations and
bound returned payloads. Search uses ripgrep when available and a Python
fallback otherwise.

`workspace_search` treats `path` as the search root. It enforces one
wall-clock deadline (`SEARCH_TEXT_DEADLINE_SECONDS`), match-work and
scan budgets, per-chat and global concurrency admission, and a linear
response payload fit (`MCP_MAX_PAYLOAD_BYTES` minus
`MCP_TOOL_RESULT_OVERHEAD_BYTES`). Exhausted work returns `ok=true` with
`truncated=true`, a typed `limit_reason` (`deadline`, `work_matches`,
`scanned_files`, `scanned_bytes`, `payload`, `result_cap`, `queue`), and `count_complete=false`. `exact_count`
scans the full work budget and costs more than a capped search. Telemetry
records query length and a keyed digest only, never raw queries or matches.

## Lifecycle

The supervisor manages the FastMCP server and observes the Cloudflare tunnel.
The canonical tunnel URL is stored in `logs/tunnel_url.txt`. Server-only
restart preserves the tunnel process and URL. Tunnel loss never causes an
automatic Cloudflare restart.

## Audit and observability

Audit records are versioned JSONL. Sensitive values are redacted. Transport
metrics track HTTP requests, MCP messages, tool calls, latency and failures.
The local-only `/debug/transport` route exposes bounded diagnostic metadata.
