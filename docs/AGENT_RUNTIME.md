# Agent Runtime MCP Integration

The BotQuangAnh Host MCP acts only as a control plane for the separate BotQuangAnh Agent Runtime. It does not run the model loop, scheduler, workers, or long-lived agent execution inside the MCP server process.

## Configuration

```env
AGENT_RUNTIME_URL=http://127.0.0.1:9420
AGENT_RUNTIME_TOKEN=
AGENT_RUNTIME_TIMEOUT_SECONDS=30
AGENT_RUNTIME_RESULT_TIMEOUT_SECONDS=60
```

`AGENT_RUNTIME_TOKEN` is sent only as a Bearer service token. The client representation, public errors, audit helpers, and tests are designed not to expose the token or a raw Authorization header.

The runtime is an optional dependency. If it is offline, the main MCP `health_check` remains healthy. `agent_runtime_health` reports `status=unavailable` or `status=degraded` with a normalized public-safe error.

## Client behavior

`app/clients/agent_runtime.py` provides one pooled `httpx.AsyncClient` with:

- validated absolute HTTP(S) base URL;
- bounded connect, read, write, and pool timeouts;
- a generated `X-Request-ID` on every request;
- optional Bearer service-token authentication;
- `Idempotency-Key` support for side-effecting requests;
- limited retries only for GET/idempotent operations and transient 502/503/504 or transport failures;
- no automatic retry for POST operations;
- normalized runtime errors and public-safe messages;
- explicit asynchronous close and async context-manager support.

## Exposed MCP tools

| Tool | Runtime operation |
|---|---|
| `agent_runtime_health` | `GET /health` and `GET /ready` |
| `agent_run_start` | `POST /v1/runs`; returns immediately with `run_id` |
| `agent_run_status` | `GET /v1/runs/{run_id}` |
| `agent_run_events` | `GET /v1/runs/{run_id}/events` with cursor and limit |
| `agent_run_message` | `POST /v1/runs/{run_id}/messages` |
| `agent_run_cancel` | `POST /v1/runs/{run_id}/cancel` |
| `agent_run_result` | `GET /v1/runs/{run_id}/result` |
| `agent_list` | `GET /v1/agents` |
| `agent_message` | `POST /v1/agents/{agent_id}/messages` |
| `agent_cancel` | `POST /v1/agents/{agent_id}/cancel` |
| `task_status` | `GET /v1/tasks/{task_id}` |
| `task_retry` | `POST /v1/tasks/{task_id}/retry` |
| `artifact_get` | Artifact metadata or one bounded content chunk |

`agent_run_start` never waits for an agent run to finish. The caller should poll `agent_run_status`, `agent_run_events`, or `agent_run_result`.

When a result is not ready and the runtime returns HTTP 409, `agent_run_result` returns:

```json
{
  "ok": true,
  "ready": false,
  "status": "pending",
  "run_id": "..."
}
```

This avoids keeping a long MCP request open.

## Create-run payload

The minimum MCP-facing fields are:

```text
objective
workspace
strategy
completion_policy
max_agents
max_tasks
max_subtask_depth
max_cost_usd
deadline
```

The tool converts the workspace string into the runtime `WorkspaceRef` shape and maps `deadline` to `deadline_at`. Optional `tenant_id`, `created_by`, `workspace_id`, read-only state, metadata, and an explicit idempotency key can be supplied when required by the runtime deployment.

If no idempotency key is provided, the MCP gateway generates one for each side-effecting request.

## Error mapping

Runtime and transport errors are mapped to the existing MCP error envelope:

```json
{
  "ok": false,
  "error": {
    "code": "RUNTIME_UNAVAILABLE",
    "message": "Agent runtime is unavailable.",
    "suggestion": "Start the agent runtime or check AGENT_RUNTIME_URL.",
    "retryable": true
  }
}
```

Supported public codes include:

```text
RUNTIME_UNAVAILABLE
RUN_NOT_FOUND
AGENT_NOT_FOUND
TASK_NOT_FOUND
ARTIFACT_NOT_FOUND
INVALID_STATE_TRANSITION
BUDGET_EXCEEDED
TOOL_PERMISSION_DENIED
AUTHENTICATION_FAILED
TIMEOUT
INTERNAL_ERROR
INVALID_ARGUMENT
```

Internal tracebacks and raw authorization credentials are never returned.

## Artifact handling

`artifact_get` returns metadata by default. Setting `include_content=true` requests only one bounded chunk using `offset` and `limit`.

- Default chunk: 262,144 bytes.
- Maximum chunk: 1,048,576 bytes.
- Large artifacts should be followed by the runtime-provided URI/path or fetched in multiple chunks.
- Binary data should not be embedded unbounded in one MCP response.

## Operator checks

```bash
pytest -q tests/test_agent_runtime_client.py tests/test_agent_runtime_tools.py
pytest -q
python -m compileall -q app
./scripts/quality_gate.sh
```

For deployment, restart only the MCP server:

```bash
bqa server restart
# or
scripts/restart_server_only.sh
```

Do not restart the supervisor or Cloudflare tunnel. Verify that the supervisor PID, tunnel PID, and public MCP URL stay unchanged while the MCP server PID changes.
