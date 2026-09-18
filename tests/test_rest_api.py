import json
import os
import subprocess
import sys


def test_rest_api_reuses_host_services_and_preserves_mcp():
    env = {
        **os.environ,
        "REQUIRE_AUTH": "false",
        "MCP_JSON_RESPONSE": "true",
        "MCP_STATELESS_HTTP": "true",
        "ATTRIBUTION_MODE": "off",
    }
    code = r'''
import json
import os
import tempfile

workspace = tempfile.mkdtemp(prefix="host-rest-api-")
os.environ["HOST_WORKSPACE_DIR"] = workspace
os.environ["HOST_RESTRICT_TO_WORKSPACE"] = "true"
os.environ["REQUIRE_AUTH"] = "false"
os.environ["ATTRIBUTION_MODE"] = "off"

from starlette.testclient import TestClient
import app.main
from app.mcp_server import mcp

app = mcp.http_app(
    path="/mcp",
    transport="streamable-http",
    json_response=False,
    stateless_http=False,
)

mcp_headers = {
    "content-type": "application/json",
    "accept": "application/json, text/event-stream",
}

with TestClient(app) as client:
    responses = {}
    responses["index"] = client.get("/api/v1")
    responses["health"] = client.get("/api/v1/health")
    responses["capabilities"] = client.get("/api/v1/capabilities")
    responses["mkdir"] = client.post(
        "/api/v1/directories", json={"path": "demo"}
    )
    responses["write"] = client.put(
        "/api/v1/files/content",
        json={"path": "demo/note.txt", "content": "hello world\n"},
    )
    responses["read"] = client.get(
        "/api/v1/files/content", params={"path": "demo/note.txt"}
    )
    responses["replace"] = client.patch(
        "/api/v1/files/content",
        json={
            "path": "demo/note.txt",
            "old": "world",
            "new": "REST",
            "expected_count": 1,
        },
    )
    responses["append"] = client.post(
        "/api/v1/files/append",
        json={"path": "demo/note.txt", "content": "ready\n"},
    )
    responses["list"] = client.get(
        "/api/v1/files", params={"path": "demo"}
    )
    responses["search"] = client.get(
        "/api/v1/search", params={"path": "demo", "query": "ready"}
    )
    responses["check"] = client.post(
        "/api/v1/commands/check", json={"command": "printf api-ok"}
    )
    responses["run"] = client.post(
        "/api/v1/commands/run",
        json={"command": "printf api-ok", "cwd": ".", "timeout_seconds": 5},
    )
    responses["knowledge"] = client.get(
        "/api/v1/knowledge", params={"section": "overview"}
    )
    responses["openapi"] = client.get("/api/v1/openapi.json")
    responses["invalid"] = client.get("/api/v1/files/content")
    responses["mcp"] = client.post(
        "/mcp",
        headers=mcp_headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "rest-test", "version": "1.0"},
            },
        },
    )

result = {
    name: {
        "status": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "json": response.json(),
    }
    for name, response in responses.items()
}
print(json.dumps(result))
'''
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=40,
        check=True,
    )
    result = json.loads(proc.stdout)

    successful = {
        "index",
        "health",
        "capabilities",
        "mkdir",
        "write",
        "read",
        "replace",
        "append",
        "list",
        "search",
        "check",
        "run",
        "knowledge",
        "openapi",
        "mcp",
    }
    for name in successful:
        assert result[name]["status"] == 200, (name, result[name])
        assert result[name]["content_type"].startswith("application/json")

    assert result["read"]["json"]["content"] == "hello world\n"
    assert result["replace"]["json"]["replacement_count"] == 1
    assert result["search"]["json"]["results"][0]["line"] == "ready"
    assert result["check"]["json"]["allowed"] is True
    assert result["run"]["json"]["stdout"] == "api-ok"
    assert result["openapi"]["json"]["openapi"] == "3.1.0"
    assert result["invalid"]["status"] == 400
    assert result["mcp"]["json"]["result"]["serverInfo"]["name"] == "BotQuangAnh Host MCP"


def test_rest_api_uses_existing_gateway_authentication():
    env = {
        **os.environ,
        "REQUIRE_AUTH": "true",
        "GATEWAY_TOKEN": "rest-test-token",
    }
    code = r'''
import json
from starlette.testclient import TestClient
import app.main
from app.mcp_server import mcp

app = mcp.http_app(path="/mcp", transport="streamable-http")
with TestClient(app) as client:
    result = {
        "healthz": client.get("/healthz").status_code,
        "missing": client.get("/api/v1/health").status_code,
        "bearer": client.get(
            "/api/v1/health",
            headers={"Authorization": "Bearer rest-test-token"},
        ).status_code,
        "header": client.get(
            "/api/v1/health",
            headers={"X-Gateway-Token": "rest-test-token"},
        ).status_code,
    }
print(json.dumps(result))
'''
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    result = json.loads(proc.stdout)
    assert result == {
        "healthz": 200,
        "missing": 401,
        "bearer": 200,
        "header": 200,
    }


def test_nonzero_host_command_is_not_an_http_server_error():
    from app.rest_api import _result_status

    result = {"ok": False, "exit_code": 7, "stdout": "", "stderr": "failed"}
    assert _result_status(result) == 200


def test_rest_command_nonzero_exit_returns_http_200_with_exit_code():
    env = {
        **os.environ,
        "REQUIRE_AUTH": "false",
        "MCP_JSON_RESPONSE": "true",
        "MCP_STATELESS_HTTP": "true",
    }
    code = r'''
import json
import os
import tempfile

os.environ["HOST_WORKSPACE_DIR"] = tempfile.mkdtemp(prefix="host-rest-nonzero-")
os.environ["HOST_RESTRICT_TO_WORKSPACE"] = "true"
os.environ["REQUIRE_AUTH"] = "false"

from starlette.testclient import TestClient
import app.main
from app.mcp_server import mcp

app = mcp.http_app(path="/mcp", transport="streamable-http")
with TestClient(app) as client:
    response = client.post(
        "/api/v1/commands/run",
        json={"command": "false", "cwd": ".", "timeout_seconds": 5},
    )
print(json.dumps({"status": response.status_code, "body": response.json()}))
'''
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    result = json.loads(proc.stdout)
    assert result["status"] == 200
    assert result["body"]["ok"] is False
    assert result["body"]["exit_code"] == 1
