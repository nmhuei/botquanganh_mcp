import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.cli.client import RESTClient
from app.cli.errors import AuthenticationCLIError, CLIError, NotFoundCLIError


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def _send(self, status, body, content_type="application/json"):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/ok":
            self._send(200, {"ok": True, "authorization": self.headers.get("Authorization")})
        elif self.path == "/bad-json":
            self._send(200, b"not-json", "text/plain")
        elif self.path == "/auth":
            self._send(401, {"error": {"message": "missing token"}})
        else:
            self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):
        if self.path == "/command":
            self._send(
                500,
                {
                    "ok": False,
                    "exit_code": 9,
                    "stdout": "",
                    "stderr": "failed",
                },
            )
        else:
            self._send(404, {"error": {"message": "not found"}})


@pytest.fixture
def http_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_client_sends_auth_and_decodes_json(http_server):
    result = RESTClient(http_server, token="abc").get("/ok")
    assert result["ok"] is True
    assert result["authorization"] == "Bearer abc"


def test_client_maps_http_errors(http_server):
    with pytest.raises(AuthenticationCLIError):
        RESTClient(http_server).get("/auth")
    with pytest.raises(NotFoundCLIError):
        RESTClient(http_server).get("/missing")


def test_client_preserves_command_failure_payload(http_server):
    result = RESTClient(http_server).post("/command", json_body={}, allow_command_failure=True)
    assert result["exit_code"] == 9
    assert result["stderr"] == "failed"


def test_client_rejects_invalid_json(http_server):
    with pytest.raises(CLIError):
        RESTClient(http_server).get("/bad-json")


def test_rest_client_rejects_non_http_and_embedded_credentials():
    import pytest

    from app.cli.errors import CLIError

    for url in (
        "file:///tmp/socket",
        "ftp://example.com",
        "https://user:" + "password@example.com",  # pragma: allowlist secret
        "https://example.com?token=value",
        "https://example.com#fragment",
    ):
        with pytest.raises(CLIError):
            RESTClient(url)
