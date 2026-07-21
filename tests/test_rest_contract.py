import json
import os
import subprocess
import sys


def test_rest_error_contract_matches_shared_taxonomy():
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
from pathlib import Path

workspace = Path(tempfile.mkdtemp(prefix="rest-contract-"))
os.environ["HOST_WORKSPACE_DIR"] = str(workspace)
os.environ["HOST_RESTRICT_TO_WORKSPACE"] = "true"
os.environ["REQUIRE_AUTH"] = "false"

from starlette.testclient import TestClient
import app.main
from app.mcp_server import mcp

app = mcp.http_app(path="/mcp", transport="streamable-http")
with TestClient(app) as client:
    missing = client.get("/api/v1/files/content", params={"path": "missing.txt"})
    first = client.put(
        "/api/v1/files/content",
        json={"path": "exists.txt", "content": "one", "overwrite": False},
    )
    conflict = client.put(
        "/api/v1/files/content",
        json={"path": "exists.txt", "content": "two", "overwrite": False},
    )
    not_directory = client.get("/api/v1/files", params={"path": "exists.txt"})
    invalid = client.get("/api/v1/files/content")

result = {
    "missing": [missing.status_code, missing.json()],
    "first": [first.status_code, first.json()],
    "conflict": [conflict.status_code, conflict.json()],
    "not_directory": [not_directory.status_code, not_directory.json()],
    "invalid": [invalid.status_code, invalid.json()],
    "workspace": str(workspace),
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
    assert result["missing"][0] == 404
    assert result["missing"][1]["error"]["code"] == "FILE_NOT_FOUND"
    assert result["workspace"] not in result["missing"][1]["error"]["message"]
    assert result["first"][0] == 200
    assert result["conflict"][0] == 409
    assert result["conflict"][1]["error"]["code"] == "FILE_EXISTS"
    assert result["not_directory"][0] == 400
    assert result["not_directory"][1]["error"]["code"] == "INVALID_ARGUMENT"
    assert result["invalid"][0] == 400
    assert result["invalid"][1]["error"]["code"] == "INVALID_ARGUMENT"


def test_auth_failure_uses_json_error_contract():
    env = {
        **os.environ,
        "REQUIRE_AUTH": "true",
        "GATEWAY_TOKEN": "contract-token",
    }
    code = r'''
import json
from starlette.testclient import TestClient
import app.main
from app.mcp_server import mcp

app = mcp.http_app(path="/mcp", transport="streamable-http")
with TestClient(app) as client:
    response = client.get("/api/v1/health")
print(json.dumps({
    "status": response.status_code,
    "content_type": response.headers.get("content-type"),
    "body": response.json(),
}))
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
    assert result["status"] == 401
    assert result["content_type"].startswith("application/json")
    assert result["body"]["error"]["code"] == "AUTH_REQUIRED"
