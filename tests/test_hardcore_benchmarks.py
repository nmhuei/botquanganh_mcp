"""Measure real tool limits without relaxing failures or mocking the measured work."""

import asyncio
import importlib
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import statistics
import sys
import tempfile
import time
import tracemalloc
from types import SimpleNamespace

import httpx
import pytest
from mcp.types import CallToolResult, TextContent

from app import config
from app.observability import MCPForensicsMiddleware
from app.tools.terminal_execute import terminal_execute
from app.tools.web_intelligence import _fetch_url, web_intelligence
from app.tools.workspace_edit import workspace_edit
from app.tools.workspace_explore import workspace_explore
from app.tools.workspace_search import workspace_search
from app.ui.ctf_fetch_result import CTF_FETCH_RESULT_WIDGET_URI


REPO = Path(__file__).resolve().parents[1]
CEILING = 512_000
LATENCY_MS = 100


def wire_bytes(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True, exclude_none=True)
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def metric(record_property, name, value):
    record_property(name, value)
    print(f"METRIC {name}={value}")


def assert_correction(result):
    assert result["ok"] is False
    assert result["truncated"] is True
    assert result["error"]["code"] == "PAYLOAD_LIMIT_EXCEEDED"
    assert result["error"]["recommendations"]
    assert wire_bytes(result) <= CEILING


@pytest.fixture
def sandbox(monkeypatch):
    """Keep generated files outside the repository and disable workspace journaling."""
    root = Path.home() / "Downloads" / "bqa-trash"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hardcore-", dir=root) as directory:
        path = Path(directory)
        monkeypatch.setattr(config, "ATTRIBUTION_MODE", "off")
        monkeypatch.setattr(config, "HOST_CHAT_WORKSPACES", False)
        monkeypatch.setattr(config, "HOST_DEFAULT_DIR", path)
        monkeypatch.setattr(config, "HOST_WORKSPACE_DIR", path)
        monkeypatch.setattr(config, "HOST_RESTRICT_TO_WORKSPACE", False)
        monkeypatch.setattr(config, "HOST_READ_SCOPE_SET", False)
        monkeypatch.setattr(config, "HOST_WRITE_SCOPE_SET", False)
        monkeypatch.setattr(config, "HOST_READ_DENY_GLOBS", ())
        yield path


@pytest.mark.parametrize("mode", ["path", "content"])
def test_search_speed_and_payload_bound(sandbox, mode, record_property):
    assert shutil.which("rg"), "Install ripgrep to run this empirical benchmark."
    kwargs = dict(path=str(REPO), mode=mode, include_hidden=True, max_matches=100)
    kwargs["path_glob" if mode == "path" else "query"] = "*.py" if mode == "path" else "def "
    durations = []
    for _ in range(5):
        start = time.perf_counter()
        result = workspace_search(**kwargs)
        durations.append((time.perf_counter() - start) * 1000)
        assert result["ok"], result
        assert result["matches"]
        assert wire_bytes(result) <= CEILING
        paths = result["matches"] if mode == "path" else [m["file"] for m in result["matches"]]
        assert all(not {".git", ".venv", "__pycache__"}.intersection(Path(p).parts) for p in paths)
    metric(record_property, f"{mode}_latency_ms", [round(v, 3) for v in durations])
    metric(record_property, f"{mode}_median_ms", round(statistics.median(durations), 3))
    metric(record_property, f"{mode}_wire_bytes", wire_bytes(result))
    assert max(durations) < LATENCY_MS, durations


def test_search_prunes_ignored_directories(sandbox, monkeypatch):
    search = importlib.import_module("app.tools.workspace_search")
    (sandbox / "visible.txt").write_text("benchmark_sentinel\n")
    for name in (".git", ".venv", "__pycache__"):
        nested = sandbox / name / "nested"
        nested.mkdir(parents=True)
        (nested / "hidden.txt").write_text("benchmark_sentinel\n")
    for mode in ("path", "content"):
        result = workspace_search(path=str(sandbox), mode=mode, include_hidden=True,
                                  query="*" if mode == "path" else "benchmark_sentinel")
        assert result["ok"], result
        assert len(result["matches"]) == 1

    visited = []
    original_walk = os.walk

    def tracked_walk(*args, **kwargs):
        for entry in original_walk(*args, **kwargs):
            visited.append(Path(entry[0]))
            yield entry

    def unavailable(*args, **kwargs):
        raise OSError("Exercise the real Python traversal fallback.")

    monkeypatch.setattr("app.search_engines.os.walk", tracked_walk)
    import app.search_engines as engines_module

    monkeypatch.setattr(engines_module.subprocess, "Popen", unavailable)
    monkeypatch.setattr("app.tools.workspace_search.shutil.which", lambda _name: None)
    result = workspace_search(path=str(sandbox), mode="path", include_hidden=True)
    assert result["ok"] and len(result["matches"]) == 1
    assert visited == [sandbox], visited


@pytest.fixture
def large_file(sandbox):
    target = sandbox / "twenty-megabytes.txt"
    with target.open("w", encoding="ascii") as stream:
        for index in range(1, 200_001):
            stream.write(f"{index:06d}:" + "x" * 92 + "\n")
    assert target.stat().st_size == 20_000_000
    return target


def test_explore_streaming_performance_large_file(large_file, record_property):
    # The public API expresses inclusive line_end=150100 as line_count=101.
    start = time.perf_counter()
    result = workspace_explore(path=str(large_file), start_line=150_000, line_count=101)
    elapsed = (time.perf_counter() - start) * 1000
    assert result["ok"], result
    assert result["start_line"] == 150_000 and result["end_line"] == 150_100
    assert result["total_lines"] == 200_000
    assert len(result["lines"]) == 101
    assert result["lines"][0]["text"].startswith("150000:")
    metric(record_property, "explore_latency_ms", round(elapsed, 3))
    metric(record_property, "explore_wire_bytes", wire_bytes(result))
    assert elapsed < LATENCY_MS
    assert wire_bytes(result) <= CEILING

    # Measure allocation separately because tracing changes execution latency.
    tracemalloc.start()
    try:
        workspace_explore(path=str(large_file), start_line=150_000, line_count=101)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    metric(record_property, "explore_peak_python_bytes", peak)
    assert peak < large_file.stat().st_size // 2


def test_explore_giant_line_cap(sandbox):
    target = sandbox / "giant-line.txt"
    target.write_text("x" * 20_000 + "\n")
    result = workspace_explore(path=str(target))
    assert result["ok"], result
    assert result["lines"][0]["text"] == "x" * 8192 + "...[line truncated]"
    assert wire_bytes(result) <= CEILING


def test_explore_large_request_self_correction(large_file, record_property):
    result = workspace_explore(path=str(large_file), line_count=100_000)
    metric(record_property, "explore_large_request_wire_bytes", wire_bytes(result))
    assert_correction(result)


def test_edit_diff_preview_and_ast_syntax_shield(sandbox, record_property):
    target = sandbox / "shield.py"
    original = "VALUE = 1\nVALUE = 1\n"
    target.write_text(original)
    result = workspace_edit(path=str(target), action="replace", old_text="VALUE = 1",
                            new_text="VALUE = 2\nEXTRA = 3", expected_count=-1)
    assert result["ok"], result
    assert target.read_text() == "VALUE = 2\nEXTRA = 3\n" * 2
    assert result["lines_changed"] == 2
    assert result["diff_preview"].startswith("--- a/shield.py\n+++ b/shield.py\n@@")
    assert "-VALUE = 1" in result["diff_preview"] and "+EXTRA = 3" in result["diff_preview"]
    assert len(result["diff_preview"].splitlines()) <= 30
    before = target.read_bytes()
    rejected = workspace_edit(path=str(target), action="write", content="def broken(")
    assert not rejected["ok"] and rejected["error"]["code"] == "SYNTAX_ERROR"
    assert target.read_bytes() == before
    json_file = sandbox / "shield.json"
    json_file.write_text('{"key": 1}\n')
    before = json_file.read_bytes()
    rejected = workspace_edit(path=str(json_file), action="write", content='{"key": }')
    assert not rejected["ok"] and rejected["error"]["code"] == "SYNTAX_ERROR"
    assert json_file.read_bytes() == before
    metric(record_property, "edit_wire_bytes", wire_bytes(result))


def test_terminal_execute_payload_truncation_and_child_reaping(sandbox, record_property):
    code = "import sys; sys.stdout.write('x' * 5_000_000)"
    result = terminal_execute(command=f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}",
                              cwd=str(sandbox), timeout_seconds=10)
    assert result["ok"], result
    assert result["output_truncated"] is True
    assert "[TRUNCATED" in result["output"]
    assert "| head" in result["output"] and "| grep" in result["output"]
    metric(record_property, "terminal_wire_bytes", wire_bytes(result))
    assert wire_bytes(result) <= CEILING

    pid_file = sandbox / "child.pid"
    command = f"sleep 100 & echo $! > {shlex.quote(str(pid_file))}; wait"
    try:
        result = terminal_execute(command=command, cwd=str(sandbox), timeout_seconds=1)
        assert result["timed_out"] is True, result
        child_pid = int(pid_file.read_text())
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            status = Path(f"/proc/{child_pid}/stat")
            if not status.exists() or status.read_text().split(")", 1)[1].split()[0] == "Z":
                break
            time.sleep(0.01)
        else:
            pytest.fail(f"Child {child_pid} remains alive after timeout.")
        metric(record_property, "terminal_timeout_duration_ms", result["duration_ms"])
    finally:
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


class CountingStream(httpx.SyncByteStream):
    def __init__(self, size, chunk_size=16_384):
        self.size = size
        self.chunk_size = chunk_size
        self.downloaded = 0
        self.closed = False

    def __iter__(self):
        while self.downloaded < self.size:
            length = min(self.chunk_size, self.size - self.downloaded)
            self.downloaded += length
            yield b"x" * length

    def close(self):
        self.closed = True


def test_web_intelligence_chunk_streaming_ceiling(sandbox, monkeypatch, record_property):
    limit = 1_048_576
    stream = CountingStream(3 * limit)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))
    with httpx.Client(transport=transport) as client:
        response, body, truncated = _fetch_url(client, "GET", "https://benchmark.invalid", limit)
    assert len(body) == limit and truncated
    assert stream.downloaded <= limit + stream.chunk_size < stream.size
    assert stream.closed and response.is_closed
    metric(record_property, "http_downloaded_bytes", stream.downloaded)
    metric(record_property, "http_retained_bytes", len(body))

    def send(client, request, **kwargs):
        assert kwargs.get("stream") is True
        return httpx.Response(200, request=request, headers={"content-type": "text/html"},
                              content=b'<html><!-- flag{hidden} --><input type="hidden" name="token" value="abc"><p>Hello</p></html>')

    monkeypatch.setattr(httpx.Client, "send", send)
    result = web_intelligence("https://benchmark.invalid")
    assert result["ok"], result
    assert result["intelligence"]["comments"] == ["flag{hidden}"]
    assert result["intelligence"]["hidden_inputs"] == [{"name": "token", "value": "abc", "id": ""}]
    assert result["intelligence"]["flags"] == ["flag{hidden}"]
    assert result["widget_uri"] == CTF_FETCH_RESULT_WIDGET_URI
    assert wire_bytes(result) <= CEILING


@pytest.mark.parametrize("variant", ["single", "multiple", "structured"])
def test_forensics_middleware_universal_512k_interception(sandbox, variant, record_property):
    if variant == "single":
        result = CallToolResult(content=[TextContent(type="text", text=json.dumps({"output": "x" * 600_000}))])
    elif variant == "multiple":
        result = CallToolResult(content=[TextContent(type="text", text="x" * 300_000) for _ in range(2)])
    else:
        result = CallToolResult(content=[TextContent(type="text", text="small")], structuredContent={"output": "x" * 600_000})
    assert wire_bytes(result) > CEILING

    async def call_next(context):
        return result

    context = SimpleNamespace(message=SimpleNamespace(name="benchmark_payload"))
    bounded = asyncio.run(MCPForensicsMiddleware().on_call_tool(context, call_next))
    metric(record_property, f"middleware_{variant}_wire_bytes", wire_bytes(bounded))
    assert bounded.isError is True
    assert wire_bytes(bounded) <= CEILING
    assert_correction(json.loads(bounded.content[0].text))
