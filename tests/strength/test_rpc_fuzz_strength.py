import json
import os
import subprocess
import sys


CORPUS_CODE = r'''
import json
from starlette.testclient import TestClient
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

deep_nested = "[" * 500 + "]" * 500
huge_string = '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{"x":"' + "A" * 2_000_000 + '"}}'

corpus = [
    ("empty_body", ""),
    ("binary_garbage", "\x00\x01\x02\xff"),
    ("truncated_json", '{"jsonrpc":"2.0","id":1,"meth'),
    ("json_null", "null"),
    ("json_number", "123"),
    ("json_array", "[1,2,3]"),
    ("wrong_version", '{"jsonrpc":"1.0","id":1,"method":"tools/list"}'),
    ("missing_method_and_id", '{"jsonrpc":"2.0"}'),
    ("id_as_object", '{"jsonrpc":"2.0","id":{"a":1},"method":"tools/list"}'),
    ("method_number", '{"jsonrpc":"2.0","id":1,"method":42}'),
    ("method_null", '{"jsonrpc":"2.0","id":1,"method":null}'),
    ("params_string", '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":"oops"}'),
    ("duplicate_keys", '{"jsonrpc":"2.0","jsonrpc":"2.0","id":1,"method":"tools/list"}'),
    ("null_byte_in_method", '{"jsonrpc":"2.0","id":1,"method":"tools\\u0000/list"}'),
    ("lone_surrogate", '{"jsonrpc":"2.0","id":1,"method":"\\ud800"}'),
    ("utf8_bom", '﻿{"jsonrpc":"2.0","id":1,"method":"tools/list"}'),
    ("nan_token", '{"jsonrpc":"2.0","id":NaN,"method":"tools/list"}'),
    ("notification_no_id", '{"jsonrpc":"2.0","method":"tools/list"}'),
    ("deep_nesting", deep_nested),
    ("huge_string_field", huge_string),
    ("unknown_tool_call", '{"jsonrpc":"2.0","id":9,"method":"tools/call","params":{"name":"does_not_exist","arguments":{}}}'),
    ("tool_args_wrong_type", '{"jsonrpc":"2.0","id":10,"method":"tools/call","params":{"name":"health_check","arguments":{"not_a_real_arg":[1,{"deep":true}]}}}'),
]

results = []
with TestClient(app) as client:
    for name, body in corpus:
        try:
            response = client.post("/mcp", content=body.encode("utf-8"), headers=headers)
            results.append({"name": name, "status": response.status_code})
        except Exception as exc:
            results.append({"name": name, "error": type(exc).__name__})
    get_response = client.get("/mcp")
    canary = []
    for payload in [
        {"jsonrpc": "2.0", "id": 101, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "strength", "version": "1.0"}}},
        {"jsonrpc": "2.0", "id": 102, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 103, "method": "tools/call", "params": {"name": "health_check", "arguments": {}}},
    ]:
        try:
            response = client.post("/mcp", json=payload, headers=headers)
            body_json = response.json()
            canary.append(response.status_code == 200 and "result" in body_json)
        except Exception:
            canary.append(False)

print(json.dumps({"results": results, "canary_ok": all(canary), "get_status": get_response.status_code}))
'''


def test_rpc_fuzz_corpus_never_crashes_the_server():
    env = {
        **os.environ,
        "REQUIRE_AUTH": "false",
        "MCP_JSON_RESPONSE": "true",
        "MCP_STATELESS_HTTP": "true",
    }
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", CORPUS_CODE],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, f"harness crashed:\n{proc.stderr[-2000:]}"
    summary = json.loads(proc.stdout)

    errored = [case for case in summary["results"] if "error" in case]
    assert not errored, f"unhandled server-side failures: {errored}"

    statuses = {
        case["name"]: case["status"]
        for case in summary["results"]
    }
    # fastmcp answers undecodable raw bytes with 500 rather than a 400 parse
    # error; tolerate exactly that known case but fail on any new 5xx.
    known_server_errors = {"binary_garbage"}
    server_errors = {
        name: status for name, status in statuses.items() if status >= 500
    }
    unexpected = set(server_errors) - known_server_errors
    assert not unexpected, f"unexpected 5xx responses for malformed input: {server_errors}"

    assert summary["canary_ok"] is True, (
        "server stopped answering valid requests after the abuse batch"
    )
