import json
import os
import subprocess
import sys


def test_streamable_http_uses_stateless_json_responses():
    env = {
        **os.environ,
        "REQUIRE_AUTH": "false",
        "MCP_JSON_RESPONSE": "true",
        "MCP_STATELESS_HTTP": "true",
    }
    code = r'''
import json
from starlette.testclient import TestClient
import app.main
from app.mcp_server import mcp

app = mcp.http_app(
    path="/mcp",
    transport="streamable-http",
    json_response=False,
    stateless_http=False,
)
headers = {
    "content-type": "application/json",
    "accept": "application/json, text/event-stream",
}
initialize = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "1.0"},
    },
}
with TestClient(app) as client:
    responses = [
        client.post("/mcp", headers=headers, json=initialize),
        client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ),
        client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "health_check", "arguments": {}},
            },
        ),
    ]

result = []
for response in responses:
    payload = response.json()
    result.append(
        {
            "status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "session_id": response.headers.get("mcp-session-id"),
            "has_result": "result" in payload,
        }
    )
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
    assert len(result) == 3
    assert all(item["status"] == 200 for item in result)
    assert all(item["content_type"].startswith("application/json") for item in result)
    assert all(item["session_id"] is None for item in result)
    assert all(item["has_result"] is True for item in result)
