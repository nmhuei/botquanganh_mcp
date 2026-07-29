import asyncio
import json

import httpx
import pytest

from app.clients.agent_runtime import AgentRuntimeClient, AgentRuntimeError


def run(coro):
    return asyncio.run(coro)


def make_client(handler, *, token="", retries=0):
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(
        transport=transport,
        base_url="http://runtime.test",
    )
    client = AgentRuntimeClient(
        "http://runtime.test",
        token=token,
        retry_attempts=retries,
        retry_backoff_seconds=0,
        client=http_client,
    )
    return client, http_client


def test_health_success_adds_request_id_and_bearer_token():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request_id"] = request.headers.get("x-request-id")
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={"status": "ok"})

    client, http_client = make_client(handler, token="service-secret")
    try:
        assert run(client.health()) == {"status": "ok"}
        assert seen["request_id"]
        assert seen["authorization"] == "Bearer service-secret"
        assert "service-secret" not in repr(client)
    finally:
        run(http_client.aclose())


def test_get_retries_transient_failure_but_post_does_not_retry():
    get_calls = 0

    def get_handler(request: httpx.Request) -> httpx.Response:
        nonlocal get_calls
        get_calls += 1
        if get_calls == 1:
            return httpx.Response(503, json={"error": {"code": "RUNTIME_UNAVAILABLE", "message": "busy"}})
        return httpx.Response(200, json={"run_id": "run-1"})

    client, http_client = make_client(get_handler, retries=1)
    try:
        assert run(client.get_run("run-1"))["run_id"] == "run-1"
        assert get_calls == 2
    finally:
        run(http_client.aclose())

    post_calls = 0

    def post_handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_calls
        post_calls += 1
        return httpx.Response(503, json={"error": {"code": "RUNTIME_UNAVAILABLE", "message": "busy"}})

    client, http_client = make_client(post_handler, retries=3)
    try:
        with pytest.raises(AgentRuntimeError) as raised:
            run(client.create_run({"objective": "x"}))
        assert raised.value.code == "RUNTIME_UNAVAILABLE"
        assert post_calls == 1
    finally:
        run(http_client.aclose())


def test_timeout_and_transport_failures_are_normalized():
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client, http_client = make_client(timeout_handler)
    try:
        with pytest.raises(AgentRuntimeError) as raised:
            run(client.health())
        assert raised.value.code == "TIMEOUT"
        assert raised.value.retryable is True
    finally:
        run(http_client.aclose())

    def transport_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client, http_client = make_client(transport_handler)
    try:
        with pytest.raises(AgentRuntimeError) as raised:
            run(client.health())
        assert raised.value.code == "RUNTIME_UNAVAILABLE"
    finally:
        run(http_client.aclose())


def test_auth_error_and_remote_message_are_token_redacted():
    token = "top-secret-token"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "ok": False,
                "error": {
                    "code": "AUTHENTICATION_FAILED",
                    "message": f"bad Bearer {token}; token={token}",
                    "request_id": "req-1",
                },
            },
        )

    client, http_client = make_client(handler, token=token)
    try:
        with pytest.raises(AgentRuntimeError) as raised:
            run(client.health())
        error = raised.value
        assert error.code == "AUTHENTICATION_FAILED"
        assert token not in error.message
        assert "[REDACTED]" in error.message
        assert error.request_id == "req-1"
    finally:
        run(http_client.aclose())


def test_invalid_json_response_is_internal_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"not-json",
            headers={"content-type": "application/json", "x-request-id": "req-json"},
        )

    client, http_client = make_client(handler)
    try:
        with pytest.raises(AgentRuntimeError) as raised:
            run(client.health())
        assert raised.value.code == "INTERNAL_ERROR"
        assert raised.value.request_id == "req-json"
    finally:
        run(http_client.aclose())


def test_endpoint_methods_use_expected_paths_queries_and_idempotency_headers():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        seen.append(
            (
                request.method,
                request.url.path,
                dict(request.url.params),
                request.headers.get("idempotency-key"),
                body,
            )
        )
        return httpx.Response(200, json={"ok": True})

    client, http_client = make_client(handler)

    async def exercise():
        await client.get_run_events("r1", after_sequence=7, limit=9)
        await client.send_run_message("r1", {"payload": {}}, idempotency_key="idem-1")
        await client.cancel_run("r1", {"reason": "x"}, idempotency_key="idem-2")
        await client.get_run_result("r1")
        await client.list_agents(run_id="r1", cursor="c1", limit=10)
        await client.get_agent("a1")
        await client.send_agent_message("a1", {"payload": {}}, idempotency_key="idem-3")
        await client.cancel_agent("a1", {"reason": "x"}, idempotency_key="idem-4")
        await client.get_task("t1")
        await client.retry_task("t1", {"reason": "x"}, idempotency_key="idem-5")
        await client.get_artifact("z1", include_content=True, offset=2, limit=3)

    try:
        run(exercise())
    finally:
        run(http_client.aclose())

    assert seen[0][:4] == ("GET", "/v1/runs/r1/events", {"after_sequence": "7", "limit": "9"}, None)
    assert seen[1][1:4] == ("/v1/runs/r1/messages", {}, "idem-1")
    assert seen[2][1:4] == ("/v1/runs/r1/cancel", {}, "idem-2")
    assert seen[3][1] == "/v1/runs/r1/result"
    assert seen[4][2] == {"limit": "10", "run_id": "r1", "cursor": "c1"}
    assert seen[-1][1:3] == ("/v1/artifacts/z1/content", {"offset": "2", "limit": "3"})


def test_error_mapping_for_not_found_and_result_not_ready():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/result"):
            return httpx.Response(409, json={"error": {"message": "result pending"}})
        return httpx.Response(404, json={"error": {"message": "missing"}})

    client, http_client = make_client(handler)
    try:
        with pytest.raises(AgentRuntimeError) as run_missing:
            run(client.get_run("r404"))
        assert run_missing.value.code == "RUN_NOT_FOUND"

        with pytest.raises(AgentRuntimeError) as task_missing:
            run(client.get_task("t404"))
        assert task_missing.value.code == "TASK_NOT_FOUND"

        with pytest.raises(AgentRuntimeError) as pending:
            run(client.get_run_result("r1"))
        assert pending.value.code == "INVALID_STATE_TRANSITION"
        assert pending.value.status_code == 409
    finally:
        run(http_client.aclose())


def test_owned_client_closes_and_injected_pool_is_reused():
    client = AgentRuntimeClient("http://runtime.test", retry_attempts=0)
    assert client.is_closed is False
    run(client.close())
    assert client.is_closed is True

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"ok": True})

    injected = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://runtime.test",
    )
    client = AgentRuntimeClient(
        "http://runtime.test", client=injected, retry_attempts=0
    )
    try:
        run(client.health())
        run(client.readiness())
        assert calls == 2
        assert client._client is injected
        run(client.close())
        assert injected.is_closed is False
    finally:
        run(injected.aclose())


def test_base_url_and_timeout_validation():
    with pytest.raises(ValueError):
        AgentRuntimeClient("file:///tmp/runtime")
    with pytest.raises(ValueError):
        AgentRuntimeClient("http://runtime.test?token=bad")
    with pytest.raises(ValueError):
        AgentRuntimeClient("http://user:password@runtime.test")
    with pytest.raises(ValueError):
        AgentRuntimeClient("http://runtime.test", timeout_seconds=0)
