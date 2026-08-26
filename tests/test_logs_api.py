import json
import os
import subprocess
import sys


def test_log_line_timestamp_best_effort_parsing():
    from app.rest_api import _log_line_timestamp

    assert (
        _log_line_timestamp("2026-08-26 10:00:00 INFO boot")
        == "2026-08-26T10:00:00+00:00"
    )
    assert (
        _log_line_timestamp("2026-08-26T11:30:05Z ERROR boom")
        == "2026-08-26T11:30:05+00:00"
    )
    assert (
        _log_line_timestamp("2026-08-26T12:45:09.123+07:00 ERROR later")
        == "2026-08-26T05:45:09.123000+00:00"
    )
    # Garbage prefixes, partial stamps, and plain text degrade to None.
    assert _log_line_timestamp("no stamp here") is None
    assert _log_line_timestamp("2026-13-99 99:99:99 nonsense") is None
    assert _log_line_timestamp("") is None


def test_logs_tail_end_to_end():
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

log_dir = Path(tempfile.mkdtemp(prefix="host-rest-logtail-"))
(log_dir / "server.log").write_text(
    "2026-08-26 10:00:00 INFO server boot\n"
    "no stamp here\n"
    "2026-08-26T11:30:05Z ERROR first failure\n"
    "2026-08-26T12:45:09.123+07:00 ERROR second failure\n",
    encoding="utf-8",
)
(log_dir / "cloudflared.log").write_text(
    "".join(f"tunnel line {index}\n" for index in range(1, 9)),
    encoding="utf-8",
)
(log_dir / "desktop-ui.log").write_text(
    "short desktop line\n" + ("x" * 3000) + "\n",
    encoding="utf-8",
)
# gateway.log and launcher.log intentionally absent on disk.

import app.rest_api as rest_api

# Point the fixed log directory at the fabricated tree; source names stay
# resolved server-side from the constant map either way.
rest_api._LOG_TAIL_BASE_DIR = log_dir

from starlette.testclient import TestClient
from app.mcp_server import mcp

app = mcp.http_app(path="/mcp", transport="streamable-http")

with TestClient(app) as client:
    default_all = client.get("/api/v1/logs/tail").json()
    single = client.get("/api/v1/logs/tail", params={"sources": "server"}).json()
    subset = client.get(
        "/api/v1/logs/tail", params={"sources": "desktop,server"}
    ).json()
    missing = client.get(
        "/api/v1/logs/tail", params={"sources": "launcher"}
    ).json()
    grep_hits = client.get(
        "/api/v1/logs/tail", params={"sources": "server", "grep": "ERROR"}
    ).json()
    grep_capped = client.get(
        "/api/v1/logs/tail",
        params={"sources": "server", "grep": "ERROR", "lines": 1},
    ).json()
    tail_capped = client.get(
        "/api/v1/logs/tail", params={"sources": "tunnel", "lines": 3}
    ).json()
    tail_uncapped = client.get(
        "/api/v1/logs/tail", params={"sources": "tunnel", "lines": 500}
    ).json()
    long_lines = client.get("/api/v1/logs/tail", params={"sources": "desktop"})
    unknown = client.get("/api/v1/logs/tail", params={"sources": "server,nope"})
    bad_lines = client.get("/api/v1/logs/tail", params={"lines": "abc"})
    index = client.get("/api/v1").json()
    schema = client.get("/api/v1/openapi.json").json()

result = {
    "default_all": default_all,
    "single": single,
    "subset": subset,
    "missing": missing,
    "grep_hits": grep_hits,
    "grep_capped": grep_capped,
    "tail_capped": tail_capped,
    "tail_uncapped": tail_uncapped,
    "long_lines": [long_lines.status_code, long_lines.json()],
    "unknown": [unknown.status_code, unknown.json()],
    "bad_lines": [bad_lines.status_code, bad_lines.json()],
    "index_paths": [entry["path"] for entry in index["endpoints"]],
    "logs_tail_openapi": schema["paths"]["/api/v1/logs/tail"]["get"],
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

    def source_names(payload: dict) -> list[str]:
        return [entry["source"] for entry in payload["sources"]]

    # Default 'all' covers exactly the sources that exist on disk; requests
    # carried no auth material, so the auth-disabled default holds too.
    assert result["default_all"]["ok"] is True
    assert source_names(result["default_all"]) == ["server", "tunnel", "desktop"]
    for entry in result["default_all"]["sources"]:
        # Relative layout only -- never an absolute filesystem path.
        assert not os.path.isabs(entry["path"])
        assert entry["path"].startswith("logs/")

    server_entry = result["single"]["sources"][0]
    assert server_entry == {
        "source": "server",
        "path": "logs/server.log",
        "exists": True,
        "truncated": False,
        "lines": [
            {"ts": "2026-08-26T10:00:00+00:00", "line": "2026-08-26 10:00:00 INFO server boot"},
            {"ts": None, "line": "no stamp here"},
            {"ts": "2026-08-26T11:30:05+00:00", "line": "2026-08-26T11:30:05Z ERROR first failure"},
            {"ts": "2026-08-26T05:45:09.123000+00:00", "line": "2026-08-26T12:45:09.123+07:00 ERROR second failure"},
        ],
    }

    # Explicit subsets keep caller order and skip nothing silently.
    assert source_names(result["subset"]) == ["desktop", "server"]

    # Missing file is a shaped empty snapshot, not a 404.
    assert result["missing"]["ok"] is True
    assert result["missing"]["sources"] == [
        {
            "source": "launcher",
            "path": "logs/launcher.log",
            "exists": False,
            "truncated": False,
            "lines": [],
        }
    ]

    # Grep filters before the window slice; matched lines keep their stamps.
    grep_entry = result["grep_hits"]["sources"][0]
    assert [item["line"] for item in grep_entry["lines"]] == [
        "2026-08-26T11:30:05Z ERROR first failure",
        "2026-08-26T12:45:09.123+07:00 ERROR second failure",
    ]
    grep_capped_entry = result["grep_capped"]["sources"][0]
    assert len(grep_capped_entry["lines"]) == 1
    assert grep_capped_entry["truncated"] is True
    assert grep_capped_entry["lines"][0]["line"].endswith("second failure")

    # Per-source line cap returns the newest window and flags truncation.
    capped = result["tail_capped"]["sources"][0]
    assert [item["line"] for item in capped["lines"]] == [
        "tunnel line 6",
        "tunnel line 7",
        "tunnel line 8",
    ]
    assert capped["truncated"] is True
    uncapped = result["tail_uncapped"]["sources"][0]
    assert len(uncapped["lines"]) == 8
    assert uncapped["truncated"] is False

    # Oversized lines are capped at 2000 chars with a marker, not dropped.
    status, body = result["long_lines"]
    assert status == 200
    desktop_entry = body["sources"][0]
    short_item, long_item = desktop_entry["lines"]
    assert short_item == {"ts": None, "line": "short desktop line"}
    assert long_item["ts"] is None
    assert len(long_item["line"]) == 2000
    assert long_item["truncated"] is True

    unknown_status, unknown_body = result["unknown"]
    assert unknown_status == 400
    assert unknown_body["error"]["code"] == "INVALID_ARGUMENT"
    assert "all" in unknown_body["error"]["message"]
    for name in ("server", "tunnel", "launcher", "audit", "desktop"):
        assert name in unknown_body["error"]["message"]

    bad_lines_status, bad_lines_body = result["bad_lines"]
    assert bad_lines_status == 400
    assert bad_lines_body["error"]["code"] == "INVALID_ARGUMENT"

    assert "/api/v1/logs/tail" in result["index_paths"]

    openapi_entry = result["logs_tail_openapi"]
    assert "not supported" in openapi_entry["description"]
    assert "follow" in openapi_entry["description"]
    parameters = {param["name"]: param for param in openapi_entry["parameters"]}
    assert set(parameters) == {"sources", "lines", "grep"}
    assert parameters["lines"]["schema"]["maximum"] == 500
