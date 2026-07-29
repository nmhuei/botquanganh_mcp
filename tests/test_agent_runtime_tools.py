import asyncio
import json

import httpx

from app.clients.agent_runtime import AgentRuntimeClient
from app.tools.agent_runtime import (
    agent_cancel,
    agent_list,
    agent_message,
    agent_run_cancel,
    agent_run_events,
    agent_run_message,
    agent_run_result,
    agent_run_start,
    agent_run_status,
    agent_runtime_health,
    artifact_get,
    close_agent_runtime_client,
    set_agent_runtime_client_for_testing,
    task_retry,
    task_status,
)


def run(coro):
    return asyncio.run(coro)


def install_client(handler):
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://runtime.test",
    )
    client = AgentRuntimeClient(
        "http://runtime.test",
        retry_attempts=0,
        client=http_client,
    )
    set_agent_runtime_client_for_testing(client)
    return http_client


def cleanup(http_client):
    run(close_agent_runtime_client())
    run(http_client.aclose())


def test_runtime_health_ready_and_degraded_when_optional_dependency_is_offline():
    def ready_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok", "path": request.url.path})

    http_client = install_client(ready_handler)
    try:
        result = run(agent_runtime_health())
        assert result["ok"] is True
        assert result["available"] is True
        assert result["ready"] is True
        assert result["status"] == "ready"
    finally:
        cleanup(http_client)

    def offline_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    http_client = install_client(offline_handler)
    try:
        result = run(agent_runtime_health())
        assert result["ok"] is True
        assert result["available"] is False
        assert result["ready"] is False
        assert result["status"] == "unavailable"
        assert result["error"]["code"] == "RUNTIME_UNAVAILABLE"
    finally:
        cleanup(http_client)


def test_agent_run_start_returns_immediately_and_builds_contract_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        seen["idempotency"] = request.headers.get("idempotency-key")
        return httpx.Response(
            202,
            json={"ok": True, "data": {"run_id": "run-123", "status": "created"}},
        )

    http_client = install_client(handler)
    try:
        result = run(
            agent_run_start(
                objective="Implement feature",
                workspace="file:///workspace/project",
                strategy="planner",
                completion_policy="all_tasks",
                max_agents=4,
                max_tasks=20,
                max_subtask_depth=3,
                max_cost_usd=12.5,
                deadline="2026-07-30T00:00:00Z",
                tenant_id="tenant-1",
                created_by="operator-1",
                workspace_id="workspace-1",
                idempotency_key="idem-run-1",
            )
        )
        assert result["ok"] is True
        assert result["accepted"] is True
        assert result["run_id"] == "run-123"
        assert seen["path"] == "/v1/runs"
        assert seen["idempotency"] == "idem-run-1"
        assert seen["body"]["workspace"] == {
            "uri": "file:///workspace/project",
            "read_only": False,
            "metadata": {},
            "workspace_id": "workspace-1",
        }
        assert seen["body"]["deadline_at"] == "2026-07-30T00:00:00Z"
        assert seen["body"]["max_cost_usd"] == 12.5
    finally:
        cleanup(http_client)


def test_run_status_events_message_cancel_and_result_pending():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, dict(request.url.params)))
        if request.url.path == "/v1/runs/r1":
            return httpx.Response(
                200,
                json={
                    "run_id": "r1",
                    "status": "running",
                    "task_count": 5,
                    "completed_task_count": 2,
                    "agents": [{"agent_id": "a1"}],
                    "usage": {"cost_usd": "1.25"},
                    "blockers": ["review"],
                },
            )
        if request.url.path.endswith("/events"):
            return httpx.Response(200, json={"items": [{"sequence": 4}]})
        if request.url.path.endswith("/messages"):
            return httpx.Response(202, json={"message_id": "m1"})
        if request.url.path.endswith("/cancel"):
            return httpx.Response(202, json={"run_id": "r1", "status": "cancelling"})
        if request.url.path.endswith("/result"):
            return httpx.Response(
                409,
                json={"ok": False, "error": {"message": "Run is not terminal."}},
            )
        raise AssertionError(request.url.path)

    http_client = install_client(handler)
    try:
        status = run(agent_run_status("r1"))
        assert status["status"] == "running"
        assert status["task_counts"] == {"total": 5, "completed": 2}
        assert status["agents"] == [{"agent_id": "a1"}]
        assert status["cost_usd"] == "1.25"
        assert status["blockers"] == ["review"]

        events = run(agent_run_events("r1", after_sequence=3, limit=10))
        assert events["ok"] is True
        assert events["events"] == {"items": [{"sequence": 4}]}

        message = run(agent_run_message("r1", "Prioritize tests"))
        assert message["accepted"] is True

        cancelled = run(agent_run_cancel("r1", reason="Operator request"))
        assert cancelled["accepted"] is True

        pending = run(agent_run_result("r1"))
        assert pending["ok"] is True
        assert pending["ready"] is False
        assert pending["status"] == "pending"

        assert ("GET", "/v1/runs/r1/events", {"after_sequence": "3", "limit": "10"}) in calls
    finally:
        cleanup(http_client)


def test_agent_task_and_artifact_tools_use_bounded_control_plane_routes():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        seen.append((request.method, request.url.path, dict(request.url.params), body))
        path = request.url.path
        if path == "/v1/agents":
            return httpx.Response(200, json={"items": [{"agent_id": "a1"}]})
        if path.endswith("/messages"):
            return httpx.Response(202, json={"message_id": "m1"})
        if path == "/v1/agents/a1/cancel":
            return httpx.Response(202, json={"agent_id": "a1", "status": "cancelling"})
        if path == "/v1/tasks/t1":
            return httpx.Response(200, json={"task_id": "t1", "status": "running"})
        if path == "/v1/tasks/t1/retry":
            return httpx.Response(202, json={"task_id": "t1", "status": "retry_pending"})
        if path == "/v1/artifacts/z1":
            return httpx.Response(200, json={"artifact_id": "z1", "uri": "file:///a"})
        if path == "/v1/artifacts/z1/content":
            return httpx.Response(200, json={"data": "abc", "next_offset": 3})
        raise AssertionError(path)

    http_client = install_client(handler)
    try:
        assert run(agent_list(run_id="r1", limit=10))["ok"] is True
        assert run(agent_message("a1", "Continue", run_id="r1"))["accepted"] is True
        assert run(agent_cancel("a1"))["accepted"] is True
        assert run(task_status("t1"))["task"]["status"] == "running"
        assert run(task_retry("t1", "Retry after fix", run_id="r1"))["accepted"] is True
        assert run(artifact_get("z1"))["artifact"]["uri"] == "file:///a"
        chunk = run(artifact_get("z1", include_content=True, offset=0, limit=1024))
        assert chunk["artifact"]["data"] == "abc"
        assert seen[-1][1:3] == (
            "/v1/artifacts/z1/content",
            {"offset": "0", "limit": "1024"},
        )
    finally:
        cleanup(http_client)


def test_tool_validation_and_runtime_error_mapping():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"ok": False, "error": {"code": "TASK_NOT_FOUND", "message": "missing"}},
        )

    http_client = install_client(handler)
    try:
        invalid = run(agent_run_start(objective="", workspace="."))
        assert invalid["ok"] is False
        assert invalid["error"]["code"] == "INVALID_ARGUMENT"

        invalid_limit = run(artifact_get("z1", include_content=True, limit=2_000_000))
        assert invalid_limit["error"]["code"] == "INVALID_ARGUMENT"

        missing = run(task_status("missing"))
        assert missing["ok"] is False
        assert missing["error"]["code"] == "TASK_NOT_FOUND"
        assert "traceback" not in str(missing).lower()
    finally:
        cleanup(http_client)
