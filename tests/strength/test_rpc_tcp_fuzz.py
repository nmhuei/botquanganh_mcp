"""True HTTP-over-TCP malformed-JSON-RPC fuzz against a live server subprocess.

The in-process variant (``test_rpc_fuzz_strength.py``) drives the ASGI app
through starlette's TestClient, so the real socket stack is never exercised.
This test launches the actual server (``fastmcp run app/main.py``) on an
ephemeral loopback port and fires the same classes of malformed payloads over
genuine TCP connections, then proves the server still serves valid traffic.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STARTUP_TIMEOUT_SECONDS = 30.0
PER_CASE_TIMEOUT_SECONDS = 15.0
PORT_RELEASE_TIMEOUT_SECONDS = 10.0

REQUEST_HEADERS = {
    "content-type": "application/json",
    "accept": "application/json, text/event-stream",
}

# The in-process test builds its corpus inside a CORPUS_CODE string executed
# via ``python -c``, so it is not importable; mirror its case list here.
DEEP_NESTED = "[" * 500 + "]" * 500
HUGE_STRING_FIELD = (
    '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{"x":"'
    + "A" * 2_000_000
    + '"}}'
)

CORPUS = [
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
    ("utf8_bom", "﻿" + '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'),
    ("nan_token", '{"jsonrpc":"2.0","id":NaN,"method":"tools/list"}'),
    ("notification_no_id", '{"jsonrpc":"2.0","method":"tools/list"}'),
    ("deep_nesting", DEEP_NESTED),
    ("huge_string_field", HUGE_STRING_FIELD),
    (
        "unknown_tool_call",
        '{"jsonrpc":"2.0","id":9,"method":"tools/call",'
        '"params":{"name":"does_not_exist","arguments":{}}}',
    ),
    (
        "tool_args_wrong_type",
        '{"jsonrpc":"2.0","id":10,"method":"tools/call",'
        '"params":{"name":"health_check","arguments":{"not_a_real_arg":[1,{"deep":true}]}}}',
    ),
]

CANARY_PAYLOADS = [
    {
        "jsonrpc": "2.0",
        "id": 101,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "strength-tcp", "version": "1.0"},
        },
    },
    {"jsonrpc": "2.0", "id": 102, "method": "tools/list", "params": {}},
    {
        "jsonrpc": "2.0",
        "id": 103,
        "method": "tools/call",
        "params": {"name": "health_check", "arguments": {}},
    },
]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _stderr_tail(stderr_fh, limit: int = 2000) -> str:
    try:
        stderr_fh.seek(0)
        return stderr_fh.read().decode("utf-8", "replace")[-limit:]
    except Exception:  # pragma: no cover - diagnostics only
        return "<stderr unavailable>"


def _wait_until_ready(proc: subprocess.Popen, port: int, stderr_tail) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    url = f"http://127.0.0.1:{port}/healthz"
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            pytest.fail(
                f"server exited early with code {proc.returncode}:\n{stderr_tail()}"
            )
        try:
            response = httpx.get(url, timeout=2.0)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    pytest.fail(f"server never became healthy on port {port}:\n{stderr_tail()}")


def _stop_process_group(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=5)


def _port_released(port: int) -> bool:
    deadline = time.monotonic() + PORT_RELEASE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                pass  # something still accepts connections
        except OSError:
            return True  # connection refused => nothing listening anymore
        time.sleep(0.25)
    return False


@pytest.fixture()
def live_server():
    port = _free_port()
    cli = REPO_ROOT / ".venv" / "bin" / "fastmcp"
    env = {
        **os.environ,
        "REQUIRE_AUTH": "false",
        "MCP_JSON_RESPONSE": "true",
        "MCP_STATELESS_HTTP": "true",
        "MCP_PORT": str(port),
    }
    # Capture output in temp files instead of pipes: a chatty server could
    # otherwise block on a full pipe while nobody reads it.
    with tempfile.TemporaryFile() as stdout_fh, tempfile.TemporaryFile() as stderr_fh:
        proc = subprocess.Popen(  # noqa: S603
            [
                str(cli),
                "run",
                "app/main.py",
                "--transport",
                "streamable-http",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--path",
                "/mcp",
                "--no-banner",
            ],
            cwd=REPO_ROOT,
            env=env,
            stdout=stdout_fh,
            stderr=stderr_fh,
            start_new_session=True,
        )
        try:
            _wait_until_ready(proc, port, lambda: _stderr_tail(stderr_fh))
            yield f"http://127.0.0.1:{port}", proc
        finally:
            _stop_process_group(proc)
            assert _port_released(port), (
                f"port {port} still accepting connections after teardown"
            )


@pytest.mark.strength
def test_rpc_tcp_fuzz_corpus_never_crashes_the_server(live_server):
    base_url, _proc = live_server

    statuses = {}
    with httpx.Client(timeout=PER_CASE_TIMEOUT_SECONDS) as client:
        for name, body in CORPUS:
            try:
                response = client.post(
                    f"{base_url}/mcp",
                    content=body.encode("utf-8"),
                    headers=REQUEST_HEADERS,
                )
            except Exception as exc:
                raise AssertionError(
                    f"[{name}] no response arrived over TCP "
                    f"(timeout={PER_CASE_TIMEOUT_SECONDS}s): "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            statuses[name] = response.status_code

        # fastmcp answers undecodable raw bytes with 500 rather than a 400
        # parse error; tolerate exactly that known case but fail on any new 5xx.
        known_server_errors = {"binary_garbage"}
        server_errors = {
            name: status for name, status in statuses.items() if status >= 500
        }
        unexpected = set(server_errors) - known_server_errors
        assert not unexpected, (
            f"unexpected 5xx responses for malformed input over TCP: {server_errors}"
        )

        canary_failures = []
        for payload in CANARY_PAYLOADS:
            try:
                response = client.post(
                    f"{base_url}/mcp", json=payload, headers=REQUEST_HEADERS
                )
                ok = response.status_code == 200 and "result" in response.json()
            except Exception as exc:  # noqa: BLE001
                ok = False
                canary_failures.append(
                    f"id={payload['id']} raised {type(exc).__name__}: {exc}"
                )
                continue
            if not ok:
                canary_failures.append(
                    f"id={payload['id']} status={response.status_code} "
                    f"body={response.text[:200]}"
                )
        assert not canary_failures, (
            "server stopped answering valid requests after the abuse batch: "
            f"{canary_failures}"
        )
