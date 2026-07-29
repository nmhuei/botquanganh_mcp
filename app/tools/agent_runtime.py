from __future__ import annotations

import asyncio
from typing import Any, Mapping
from uuid import uuid4

from app.clients.agent_runtime import AgentRuntimeClient, AgentRuntimeError
from app.config import (
    AGENT_RUNTIME_RESULT_TIMEOUT_SECONDS,
    AGENT_RUNTIME_TIMEOUT_SECONDS,
    AGENT_RUNTIME_TOKEN,
    AGENT_RUNTIME_URL,
)
from app.error_contract import format_error_code
from app.logging_audit import redact_sensitive_data
from app.mcp_server import mcp

AGENT_RUNTIME_TOOLS = [
    "agent_runtime_health",
    "agent_run_start",
    "agent_run_status",
    "agent_run_events",
    "agent_run_message",
    "agent_run_cancel",
    "agent_run_result",
    "agent_list",
    "agent_message",
    "agent_cancel",
    "task_status",
    "task_retry",
    "artifact_get",
]

_client: AgentRuntimeClient | None = None
_client_lock = asyncio.Lock()


def _runtime_error_result(exc: AgentRuntimeError) -> dict[str, Any]:
    extra: dict[str, Any] = {"retryable": exc.retryable}
    if exc.status_code is not None:
        extra["http_status"] = exc.status_code
    if exc.request_id:
        extra["request_id"] = exc.request_id
    if exc.details is not None:
        extra["details"] = redact_sensitive_data(exc.details)
    return format_error_code(exc.code, message=exc.message, extra=extra)


def _validate_non_empty(value: str, name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{name} must be non-empty")
    if len(normalized) > 4096:
        raise ValueError(f"{name} cannot exceed 4096 characters")
    return normalized


def _validate_limit(value: int, *, name: str, minimum: int, maximum: int) -> int:
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _validation_error(exc: Exception) -> dict[str, Any]:
    return format_error_code("INVALID_ARGUMENT", message=str(exc))


def _unwrap(data: Any) -> Any:
    if isinstance(data, Mapping) and data.get("ok") is True and "data" in data:
        return data["data"]
    return data


def _extract_id(data: Any, field: str) -> str | None:
    payload = _unwrap(data)
    if isinstance(payload, Mapping) and payload.get(field) is not None:
        return str(payload[field])
    return None


async def get_agent_runtime_client() -> AgentRuntimeClient:
    global _client
    if _client is not None and not _client.is_closed:
        return _client
    async with _client_lock:
        if _client is None or _client.is_closed:
            _client = AgentRuntimeClient(
                AGENT_RUNTIME_URL,
                token=AGENT_RUNTIME_TOKEN,
                timeout_seconds=AGENT_RUNTIME_TIMEOUT_SECONDS,
                result_timeout_seconds=AGENT_RUNTIME_RESULT_TIMEOUT_SECONDS,
            )
    return _client


async def close_agent_runtime_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def set_agent_runtime_client_for_testing(client: AgentRuntimeClient | None) -> None:
    global _client
    _client = client


@mcp.tool(
    name="agent_runtime_health",
    description="Check agent runtime liveness and readiness without failing MCP health.",
)
async def agent_runtime_health() -> dict[str, Any]:
    try:
        client = await get_agent_runtime_client()
        health = await client.health()
    except (AgentRuntimeError, ValueError) as exc:
        error = (
            _runtime_error_result(exc)["error"]
            if isinstance(exc, AgentRuntimeError)
            else _validation_error(exc)["error"]
        )
        return {
            "ok": True,
            "available": False,
            "ready": False,
            "status": "unavailable",
            "optional_dependency": True,
            "error": error,
        }

    try:
        readiness = await client.readiness()
    except AgentRuntimeError as exc:
        return {
            "ok": True,
            "available": True,
            "ready": False,
            "status": "degraded",
            "optional_dependency": True,
            "health": health,
            "error": _runtime_error_result(exc)["error"],
        }

    return {
        "ok": True,
        "available": True,
        "ready": True,
        "status": "ready",
        "optional_dependency": True,
        "health": health,
        "readiness": readiness,
    }


@mcp.tool(
    name="agent_run_start",
    description=(
        "Start an asynchronous agent run and return its run_id immediately. "
        "This control-plane call never waits for run completion."
    ),
)
async def agent_run_start(
    objective: str,
    workspace: str,
    strategy: str = "planner",
    completion_policy: str = "all_tasks",
    max_agents: int = 8,
    max_tasks: int = 256,
    max_subtask_depth: int = 4,
    max_cost_usd: float | None = None,
    deadline: str | None = None,
    tenant_id: str | None = None,
    created_by: str | None = None,
    workspace_id: str | None = None,
    workspace_read_only: bool = False,
    workspace_metadata: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    try:
        objective = _validate_non_empty(objective, "objective")
        workspace = _validate_non_empty(workspace, "workspace")
        strategy = _validate_non_empty(strategy, "strategy")
        completion_policy = _validate_non_empty(
            completion_policy, "completion_policy"
        )
        _validate_limit(max_agents, name="max_agents", minimum=1, maximum=256)
        _validate_limit(max_tasks, name="max_tasks", minimum=1, maximum=100_000)
        _validate_limit(
            max_subtask_depth,
            name="max_subtask_depth",
            minimum=0,
            maximum=64,
        )
        if max_cost_usd is not None and max_cost_usd < 0:
            raise ValueError("max_cost_usd cannot be negative")
        if deadline is not None:
            deadline = _validate_non_empty(deadline, "deadline")

        request_key = idempotency_key or f"mcp-run-{uuid4()}"
        workspace_ref: dict[str, Any] = {
            "uri": workspace,
            "read_only": workspace_read_only,
            "metadata": workspace_metadata or {},
        }
        if workspace_id:
            workspace_ref["workspace_id"] = workspace_id

        payload: dict[str, Any] = {
            "objective": objective,
            "strategy": strategy,
            "completion_policy": completion_policy,
            "workspace": workspace_ref,
            "max_agents": max_agents,
            "max_tasks": max_tasks,
            "max_subtask_depth": max_subtask_depth,
            "idempotency_key": request_key,
        }
        if max_cost_usd is not None:
            payload["max_cost_usd"] = max_cost_usd
        if deadline is not None:
            payload["deadline_at"] = deadline
        if tenant_id:
            payload["tenant_id"] = tenant_id
        if created_by:
            payload["created_by"] = created_by

        client = await get_agent_runtime_client()
        response = await client.create_run(payload, idempotency_key=request_key)
        run_id = _extract_id(response, "run_id")
        return {
            "ok": True,
            "accepted": True,
            "run_id": run_id,
            "run": _unwrap(response),
        }
    except AgentRuntimeError as exc:
        return _runtime_error_result(exc)
    except (TypeError, ValueError) as exc:
        return _validation_error(exc)


@mcp.tool(
    name="agent_run_status",
    description="Get run status, task counts, agents, usage/cost, and blockers.",
)
async def agent_run_status(run_id: str) -> dict[str, Any]:
    try:
        run_id = _validate_non_empty(run_id, "run_id")
        client = await get_agent_runtime_client()
        response = await client.get_run(run_id)
        run = _unwrap(response)
        projection = run if isinstance(run, Mapping) else {}
        usage = projection.get("usage", {})
        cost = projection.get("cost_usd")
        if cost is None and isinstance(usage, Mapping):
            cost = usage.get("cost_usd")
        return {
            "ok": True,
            "run_id": run_id,
            "status": projection.get("status"),
            "task_counts": projection.get(
                "task_counts",
                {
                    "total": projection.get("task_count", 0),
                    "completed": projection.get("completed_task_count", 0),
                },
            ),
            "agents": projection.get("agents", []),
            "usage": usage,
            "cost_usd": cost,
            "blockers": projection.get("blockers", []),
            "run": run,
        }
    except AgentRuntimeError as exc:
        return _runtime_error_result(exc)
    except (TypeError, ValueError) as exc:
        return _validation_error(exc)


@mcp.tool(
    name="agent_run_events",
    description="Get ordered run events after a sequence cursor.",
)
async def agent_run_events(
    run_id: str, after_sequence: int = 0, limit: int = 100
) -> dict[str, Any]:
    try:
        run_id = _validate_non_empty(run_id, "run_id")
        _validate_limit(
            after_sequence,
            name="after_sequence",
            minimum=0,
            maximum=2_147_483_647,
        )
        _validate_limit(limit, name="limit", minimum=1, maximum=500)
        client = await get_agent_runtime_client()
        response = await client.get_run_events(
            run_id, after_sequence=after_sequence, limit=limit
        )
        return {
            "ok": True,
            "run_id": run_id,
            "after_sequence": after_sequence,
            "limit": limit,
            "events": _unwrap(response),
        }
    except AgentRuntimeError as exc:
        return _runtime_error_result(exc)
    except (TypeError, ValueError) as exc:
        return _validation_error(exc)


def _message_body(
    *,
    instruction: str,
    message_type: str,
    run_id: str | None,
    sender_agent_id: str | None,
    recipient_agent_id: str | None,
    task_id: str | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"instruction": instruction}
    if metadata:
        payload.update(metadata)
    body: dict[str, Any] = {
        "message_type": message_type,
        "payload": payload,
    }
    if run_id:
        body["run_id"] = run_id
    if sender_agent_id:
        body["sender_agent_id"] = sender_agent_id
    if recipient_agent_id:
        body["recipient_agent_id"] = recipient_agent_id
    if task_id:
        body["task_id"] = task_id
    return body


@mcp.tool(
    name="agent_run_message",
    description="Send an instruction or broadcast into an active run.",
)
async def agent_run_message(
    run_id: str,
    instruction: str,
    message_type: str = "broadcast",
    sender_agent_id: str | None = None,
    task_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    try:
        run_id = _validate_non_empty(run_id, "run_id")
        instruction = _validate_non_empty(instruction, "instruction")
        message_type = _validate_non_empty(message_type, "message_type")
        request_key = idempotency_key or f"mcp-run-message-{uuid4()}"
        body = _message_body(
            instruction=instruction,
            message_type=message_type,
            run_id=run_id,
            sender_agent_id=sender_agent_id,
            recipient_agent_id=None,
            task_id=task_id,
            metadata=metadata,
        )
        body["idempotency_key"] = request_key
        client = await get_agent_runtime_client()
        response = await client.send_run_message(
            run_id, body, idempotency_key=request_key
        )
        return {"ok": True, "accepted": True, "message": _unwrap(response)}
    except AgentRuntimeError as exc:
        return _runtime_error_result(exc)
    except (TypeError, ValueError) as exc:
        return _validation_error(exc)


@mcp.tool(name="agent_run_cancel", description="Cancel an agent run asynchronously.")
async def agent_run_cancel(
    run_id: str,
    reason: str = "Cancelled by MCP operator.",
    requested_by: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    try:
        run_id = _validate_non_empty(run_id, "run_id")
        reason = _validate_non_empty(reason, "reason")
        request_key = idempotency_key or f"mcp-run-cancel-{uuid4()}"
        body: dict[str, Any] = {
            "run_id": run_id,
            "reason": reason,
            "idempotency_key": request_key,
        }
        if requested_by:
            body["requested_by"] = requested_by
        client = await get_agent_runtime_client()
        response = await client.cancel_run(
            run_id, body, idempotency_key=request_key
        )
        return {
            "ok": True,
            "accepted": True,
            "run_id": run_id,
            "run": _unwrap(response),
        }
    except AgentRuntimeError as exc:
        return _runtime_error_result(exc)
    except (TypeError, ValueError) as exc:
        return _validation_error(exc)


@mcp.tool(
    name="agent_run_result",
    description="Get a run result without holding the MCP request open while pending.",
)
async def agent_run_result(run_id: str) -> dict[str, Any]:
    try:
        run_id = _validate_non_empty(run_id, "run_id")
        client = await get_agent_runtime_client()
        response = await client.get_run_result(run_id)
        return {
            "ok": True,
            "ready": True,
            "run_id": run_id,
            "result": _unwrap(response),
        }
    except AgentRuntimeError as exc:
        if exc.code == "INVALID_STATE_TRANSITION" and exc.status_code == 409:
            return {
                "ok": True,
                "ready": False,
                "run_id": run_id,
                "status": "pending",
                "message": exc.message,
                "request_id": exc.request_id,
            }
        return _runtime_error_result(exc)
    except (TypeError, ValueError) as exc:
        return _validation_error(exc)


@mcp.tool(name="agent_list", description="List runtime agents with optional run filter.")
async def agent_list(
    run_id: str | None = None,
    cursor: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    try:
        if run_id is not None:
            run_id = _validate_non_empty(run_id, "run_id")
        if cursor is not None:
            cursor = _validate_non_empty(cursor, "cursor")
        _validate_limit(limit, name="limit", minimum=1, maximum=500)
        client = await get_agent_runtime_client()
        response = await client.list_agents(
            run_id=run_id, cursor=cursor, limit=limit
        )
        return {"ok": True, "agents": _unwrap(response)}
    except AgentRuntimeError as exc:
        return _runtime_error_result(exc)
    except (TypeError, ValueError) as exc:
        return _validation_error(exc)


@mcp.tool(name="agent_message", description="Send a direct instruction to an agent.")
async def agent_message(
    agent_id: str,
    instruction: str,
    run_id: str | None = None,
    sender_agent_id: str | None = None,
    message_type: str = "direct",
    task_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    try:
        agent_id = _validate_non_empty(agent_id, "agent_id")
        instruction = _validate_non_empty(instruction, "instruction")
        message_type = _validate_non_empty(message_type, "message_type")
        request_key = idempotency_key or f"mcp-agent-message-{uuid4()}"
        body = _message_body(
            instruction=instruction,
            message_type=message_type,
            run_id=run_id,
            sender_agent_id=sender_agent_id,
            recipient_agent_id=agent_id,
            task_id=task_id,
            metadata=metadata,
        )
        body["idempotency_key"] = request_key
        client = await get_agent_runtime_client()
        response = await client.send_agent_message(
            agent_id, body, idempotency_key=request_key
        )
        return {"ok": True, "accepted": True, "message": _unwrap(response)}
    except AgentRuntimeError as exc:
        return _runtime_error_result(exc)
    except (TypeError, ValueError) as exc:
        return _validation_error(exc)


@mcp.tool(name="agent_cancel", description="Cancel a runtime agent asynchronously.")
async def agent_cancel(
    agent_id: str,
    reason: str = "Cancelled by MCP operator.",
    requested_by: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    try:
        agent_id = _validate_non_empty(agent_id, "agent_id")
        reason = _validate_non_empty(reason, "reason")
        request_key = idempotency_key or f"mcp-agent-cancel-{uuid4()}"
        body: dict[str, Any] = {
            "reason": reason,
            "idempotency_key": request_key,
        }
        if requested_by:
            body["requested_by"] = requested_by
        client = await get_agent_runtime_client()
        response = await client.cancel_agent(
            agent_id, body, idempotency_key=request_key
        )
        return {
            "ok": True,
            "accepted": True,
            "agent_id": agent_id,
            "agent": _unwrap(response),
        }
    except AgentRuntimeError as exc:
        return _runtime_error_result(exc)
    except (TypeError, ValueError) as exc:
        return _validation_error(exc)


@mcp.tool(name="task_status", description="Get a runtime task status projection.")
async def task_status(task_id: str) -> dict[str, Any]:
    try:
        task_id = _validate_non_empty(task_id, "task_id")
        client = await get_agent_runtime_client()
        response = await client.get_task(task_id)
        return {"ok": True, "task_id": task_id, "task": _unwrap(response)}
    except AgentRuntimeError as exc:
        return _runtime_error_result(exc)
    except (TypeError, ValueError) as exc:
        return _validation_error(exc)


@mcp.tool(name="task_retry", description="Request an asynchronous retry for a task.")
async def task_retry(
    task_id: str,
    reason: str,
    run_id: str | None = None,
    requested_by: str | None = None,
    reset_output: bool = False,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    try:
        task_id = _validate_non_empty(task_id, "task_id")
        reason = _validate_non_empty(reason, "reason")
        request_key = idempotency_key or f"mcp-task-retry-{uuid4()}"
        body: dict[str, Any] = {
            "task_id": task_id,
            "reason": reason,
            "reset_output": reset_output,
            "idempotency_key": request_key,
        }
        if run_id:
            body["run_id"] = run_id
        if requested_by:
            body["requested_by"] = requested_by
        client = await get_agent_runtime_client()
        response = await client.retry_task(
            task_id, body, idempotency_key=request_key
        )
        return {
            "ok": True,
            "accepted": True,
            "task_id": task_id,
            "task": _unwrap(response),
        }
    except AgentRuntimeError as exc:
        return _runtime_error_result(exc)
    except (TypeError, ValueError) as exc:
        return _validation_error(exc)


@mcp.tool(
    name="artifact_get",
    description=(
        "Get artifact metadata or one bounded content chunk. Large binary content "
        "must be fetched in chunks or by the runtime-provided URI/path."
    ),
)
async def artifact_get(
    artifact_id: str,
    include_content: bool = False,
    offset: int = 0,
    limit: int = 262_144,
) -> dict[str, Any]:
    try:
        artifact_id = _validate_non_empty(artifact_id, "artifact_id")
        _validate_limit(offset, name="offset", minimum=0, maximum=2_147_483_647)
        _validate_limit(limit, name="limit", minimum=1, maximum=1_048_576)
        client = await get_agent_runtime_client()
        response = await client.get_artifact(
            artifact_id,
            include_content=include_content,
            offset=offset,
            limit=limit,
        )
        return {
            "ok": True,
            "artifact_id": artifact_id,
            "include_content": include_content,
            "offset": offset if include_content else None,
            "limit": limit if include_content else None,
            "artifact": _unwrap(response),
        }
    except AgentRuntimeError as exc:
        return _runtime_error_result(exc)
    except (TypeError, ValueError) as exc:
        return _validation_error(exc)
