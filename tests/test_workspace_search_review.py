"""Review findings regression coverage for workspace search resilience."""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def _bind(tmp_path, monkeypatch, chat_id="review-chat"):
    from app.chat_workspace import WorkspaceManager

    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "off")
    return chat_id


def test_shared_capacity_singleton_reset_and_dynamic(monkeypatch):
    from app import search_runtime as runtime

    runtime.reset_search_capacity_for_tests()
    monkeypatch.setattr("app.config.WORKSPACE_SEARCH_MAX_CONCURRENT", 3)
    monkeypatch.setattr("app.config.WORKSPACE_SEARCH_MAX_PER_CHAT", 2)
    monkeypatch.setattr("app.config.WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS", 0.01)
    first = runtime.default_search_capacity()
    second = runtime.default_search_capacity()
    assert first is second
    monkeypatch.setattr("app.config.WORKSPACE_SEARCH_MAX_CONCURRENT", 5)
    third = runtime.default_search_capacity()
    assert third is first
    assert third.snapshot()["global_limit"] == 5.0
    runtime.reset_search_capacity_for_tests()
    fourth = runtime.default_search_capacity()
    assert fourth is not first


def test_tool_global_rejection_concurrent(tmp_path, monkeypatch):
    from app import search_runtime as runtime
    from app.tools.workspace_search import workspace_search

    _bind(tmp_path, monkeypatch)
    (tmp_path / "a.txt").write_text("needle\n", encoding="utf-8")
    runtime.reset_search_capacity_for_tests()
    monkeypatch.setattr("app.config.WORKSPACE_SEARCH_MAX_CONCURRENT", 1)
    monkeypatch.setattr("app.config.WORKSPACE_SEARCH_MAX_PER_CHAT", 10)
    monkeypatch.setattr("app.config.WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS", 0)
    holder = runtime.default_search_capacity()
    lease = holder.acquire("holder-chat")
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(workspace_search, query="needle", path=str(tmp_path), chat_id="other-chat")
                for _ in range(2)
            ]
            results = [f.result(timeout=10) for f in futures]
        assert all(r.get("limit_reason") == "queue" for r in results)
        assert all(r.get("truncated") is True for r in results)
        assert all(r["error"]["code"] == "SERVICE_BUSY" for r in results)
    finally:
        lease.release()
        runtime.reset_search_capacity_for_tests()


def test_tool_per_chat_rejection_concurrent(tmp_path, monkeypatch):
    from app import search_runtime as runtime
    from app.tools.workspace_search import workspace_search

    _bind(tmp_path, monkeypatch)
    (tmp_path / "a.txt").write_text("needle\n", encoding="utf-8")
    runtime.reset_search_capacity_for_tests()
    monkeypatch.setattr("app.config.WORKSPACE_SEARCH_MAX_CONCURRENT", 10)
    monkeypatch.setattr("app.config.WORKSPACE_SEARCH_MAX_PER_CHAT", 1)
    monkeypatch.setattr("app.config.WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS", 0)
    holder = runtime.default_search_capacity()
    lease = holder.acquire("chat-a")
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            busy_future = pool.submit(workspace_search, query="needle", path=str(tmp_path), chat_id="chat-a")
            ok_future = pool.submit(workspace_search, query="needle", path=str(tmp_path), chat_id="chat-b")
            busy = busy_future.result(timeout=10)
            ok_result = ok_future.result(timeout=10)
        assert busy["error"]["code"] == "SERVICE_BUSY"
        assert busy["limit_reason"] == "queue"
        assert ok_result["ok"] is True
    finally:
        lease.release()
        runtime.reset_search_capacity_for_tests()


def test_ripgrep_silent_deadline_elapsed_and_cleanup(monkeypatch):
    import app.search_engines as engines
    from app.search_models import SearchLimitReason

    read_fd, write_fd = os.pipe()
    terminated = {"value": False}
    reaped = {"value": False}

    class FakeStdout:
        def fileno(self):
            return read_fd

        def close(self):
            return None

    class FakeStderr:
        def read(self, *args, **kwargs):
            return ""

    class FakeProcess:
        stdout = FakeStdout()
        stderr = FakeStderr()
        returncode = None
        pid = 999998

        def poll(self):
            return None

        def wait(self, timeout=None):
            reaped["value"] = True
            return 0

        def kill(self):
            terminated["value"] = True

    monkeypatch.setattr(engines.subprocess, "Popen", lambda *a, **k: FakeProcess())
    monkeypatch.setattr(
        engines.search_runtime, "terminate_process_group", lambda p: terminated.__setitem__("value", True)
    )
    orig_reap = engines.search_runtime.reap_process

    def tracking_reap(proc, timeout_seconds=None):
        reaped["value"] = True
        return orig_reap(proc, timeout_seconds=timeout_seconds)

    monkeypatch.setattr(engines.search_runtime, "reap_process", tracking_reap)
    monkeypatch.setattr(engines.config, "SEARCH_TEXT_DEADLINE_SECONDS", 0.05)
    monkeypatch.setattr(engines.config, "WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS", 0.01)
    # Keep the test focused on the child-process reader. A real inventory of
    # the repository can consume the short test deadline before Popen runs.
    monkeypatch.setattr(
        engines,
        "_inventory_scan_bounds",
        lambda root, include_hidden, deadline: (0, 0, None),
    )
    try:
        started = time.monotonic()
        outcome = engines.run_ripgrep_search(
            root=Path("."), query="needle", regex=False, case_sensitive=False,
            max_matches=10, include_hidden=False, max_work_matches=100000,
        )
        elapsed = time.monotonic() - started
    finally:
        try:
            os.close(read_fd)
        except OSError:
            pass
        try:
            os.close(write_fd)
        except OSError:
            pass
    assert outcome.limit_reason is SearchLimitReason.DEADLINE
    assert terminated["value"] is True
    assert reaped["value"] is True
    assert elapsed < 2.0
    assert elapsed >= 0.04


def test_no_literal_process_timeouts_in_sources():
    root = Path(__file__).resolve().parents[1]
    for relative in [
        "app/search_engines.py",
        "app/search_runtime.py",
        "app/tools/workspace_search.py",
        "app/tools_common.py",
        "app/observability.py",
    ]:
        text = (root / relative).read_text(encoding="utf-8")
        assert "timeout=15" not in text, relative
        assert "timeout_seconds=5.0" not in text, relative
        assert "timeout_seconds = 5.0" not in text, relative
    tools_common = (root / "app/tools_common.py").read_text(encoding="utf-8")
    assert "while kept" not in tools_common
    workspace_search = (root / "app/tools/workspace_search.py").read_text(encoding="utf-8")
    assert "matches.pop()" not in workspace_search


def test_scanned_limits_on_ripgrep_path(monkeypatch):
    import app.search_engines as engines
    from app.search_models import SearchLimitReason

    def make_fake(summary_searches, summary_bytes):
        class FakeStdout:
            def __iter__(self):
                yield '{"type":"match","data":{"path":{"text":"a.txt"},"line_number":1,"lines":{"text":"needle\\n"}}}\n'
                yield (
                    '{"type":"summary","data":{"stats":{"searches":%d,"bytes_searched":%d}}}\n'
                    % (summary_searches, summary_bytes)
                )

            def close(self):
                return None

            def fileno(self):
                raise OSError("no fileno")

        class FakeStderr:
            def read(self, *args, **kwargs):
                return ""

        class FakeProcess:
            stdout = FakeStdout()
            stderr = FakeStderr()
            returncode = 0

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

            def kill(self):
                return None

        return FakeProcess()

    monkeypatch.setattr(engines.config, "SEARCH_TEXT_DEADLINE_SECONDS", 5.0)
    monkeypatch.setattr(engines.config, "WORKSPACE_SEARCH_MAX_SCANNED_FILES", 1)
    monkeypatch.setattr(engines.config, "WORKSPACE_SEARCH_MAX_SCANNED_BYTES", 100000000)
    monkeypatch.setattr(
        engines.subprocess, "Popen", lambda *a, **k: make_fake(10, 10)
    )
    outcome = engines.run_ripgrep_search(
        root=Path("."), query="needle", regex=False, case_sensitive=False,
        max_matches=10, include_hidden=False, max_work_matches=100000,
    )
    assert outcome.limit_reason is SearchLimitReason.SCANNED_FILES
    assert outcome.count_complete is False

    monkeypatch.setattr(engines.config, "WORKSPACE_SEARCH_MAX_SCANNED_FILES", 100000)
    monkeypatch.setattr(engines.config, "WORKSPACE_SEARCH_MAX_SCANNED_BYTES", 1)
    monkeypatch.setattr(
        engines.subprocess, "Popen", lambda *a, **k: make_fake(1, 999999)
    )
    outcome = engines.run_ripgrep_search(
        root=Path("."), query="needle", regex=False, case_sensitive=False,
        max_matches=10, include_hidden=False, max_work_matches=100000,
    )
    assert outcome.limit_reason is SearchLimitReason.SCANNED_BYTES


def test_distinct_limit_reasons():
    from app.search_models import SearchLimitReason

    values = {item.value for item in SearchLimitReason}
    assert {"deadline", "work_matches", "scanned_files", "scanned_bytes", "payload", "result_cap", "queue"} <= values


def test_payload_tight_unicode_many(monkeypatch):
    import json as json_module
    from app import tools_common

    matches = [
        {"file": f"f{i}.txt", "line": i, "text": "héllo " + ("ü" * 2000)}
        for i in range(500)
    ]
    envelope = {
        "ok": True, "mode": "content", "matches": matches,
        "truncated": False, "returned_matches": len(matches),
    }
    calls = {"count": 0}
    orig_dumps = json_module.dumps

    def tracking_dumps(*args, **kwargs):
        calls["count"] += 1
        return orig_dumps(*args, **kwargs)

    monkeypatch.setattr(tools_common.json, "dumps", tracking_dumps)
    result = tools_common.fit_json_list_response(envelope, "matches", 512000)
    final_bytes = len(orig_dumps(result, ensure_ascii=False).encode("utf-8"))
    assert final_bytes <= 512000
    assert result["truncated"] is True
    assert result["limit_reason"] == "payload"
    assert calls["count"] <= len(matches) + 5
    assert result["matches"][0]["file"] == "f0.txt"

    tight = tools_common.fit_json_list_response(
        {"ok": True, "matches": [{"a": "x" * 500}], "truncated": False}, "matches", 200
    )
    assert tight["matches"] == []
    assert tight["truncated"] is True
    assert len(orig_dumps(tight, ensure_ascii=False).encode("utf-8")) <= 200 or tight["matches"] == []


def test_bridge_ceiling_dynamic(monkeypatch):
    from app.tools_common import bridge_payload_ceiling, enforce_bridge_payload_limit, search_response_budget

    monkeypatch.setattr("app.config.MCP_MAX_PAYLOAD_BYTES", 5000)
    monkeypatch.setattr("app.config.MCP_TOOL_RESULT_OVERHEAD_BYTES", 100)
    assert bridge_payload_ceiling() == 5000
    assert search_response_budget() == 4900
    payload = {"ok": True, "data": "x" * 6000}
    bounded = enforce_bridge_payload_limit(payload, tool_name="workspace_search")
    assert bounded["ok"] is False
    assert bounded["limit_bytes"] == 5000


def test_omitted_max_matches_uses_config(tmp_path, monkeypatch):
    from app.tools.workspace_search import workspace_search

    _bind(tmp_path, monkeypatch)
    monkeypatch.setattr("app.config.WORKSPACE_SEARCH_DEFAULT_MAX_MATCHES", 3)
    (tmp_path / "hits.txt").write_text("needle\n" * 10, encoding="utf-8")
    res = workspace_search(query="needle", path=str(tmp_path))
    assert res["ok"] is True
    assert res["returned_matches"] == 3


def test_path_false_truncation_at_cap(tmp_path, monkeypatch):
    from app.tools.workspace_search import workspace_search

    _bind(tmp_path, monkeypatch)
    fixture = tmp_path / "paths"
    fixture.mkdir()
    (fixture / "a.py").write_text("x\n", encoding="utf-8")
    (fixture / "b.py").write_text("x\n", encoding="utf-8")
    res = workspace_search(path=str(fixture), mode="path", path_glob="*.py", max_matches=2)
    assert res["ok"] is True
    assert len(res["matches"]) == 2
    assert res["truncated"] is False
    assert res.get("limit_reason") is None
    assert res["count_complete"] is True


def test_path_mode_deny_and_safe_traversal(tmp_path, monkeypatch):
    import app.config as config_module
    from app.tools.workspace_search import workspace_search

    _bind(tmp_path, monkeypatch)
    monkeypatch.setattr(config_module, "HOST_READ_DENY_GLOBS", ["*hidden.py"])
    secret_dir = tmp_path / "secret"
    secret_dir.mkdir()
    (secret_dir / "hidden.py").write_text("x\n", encoding="utf-8")
    (tmp_path / "visible.py").write_text("x\n", encoding="utf-8")
    link = tmp_path / "linkdir"
    try:
        link.symlink_to(secret_dir, target_is_directory=True)
    except OSError:
        pass
    res = workspace_search(path=str(tmp_path), mode="path", path_glob="*.py", max_matches=10)
    assert res["ok"] is True
    joined = "\n".join(res["matches"])
    assert "secret" not in joined
    assert "visible.py" in joined


def test_qml_has_all_keys_and_loads_current():
    root = Path(__file__).resolve().parents[1]
    qml = (root / "app/qml_ui/qml/SettingsPage.qml").read_text(encoding="utf-8")
    required = [
        "SEARCH_TEXT_DEADLINE_SECONDS",
        "WORKSPACE_SEARCH_MAX_WORK_MATCHES",
        "WORKSPACE_SEARCH_MAX_SCANNED_FILES",
        "WORKSPACE_SEARCH_MAX_SCANNED_BYTES",
        "WORKSPACE_SEARCH_MAX_CONCURRENT",
        "WORKSPACE_SEARCH_MAX_PER_CHAT",
        "WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS",
        "WORKSPACE_SEARCH_DEFAULT_MAX_MATCHES",
        "WORKSPACE_SEARCH_MAX_RETURNED_MATCHES",
        "WORKSPACE_SEARCH_MAX_LINE_CHARS",
        "MCP_MAX_PAYLOAD_BYTES",
        "MCP_TOOL_RESULT_OVERHEAD_BYTES",
    ]
    for key in required:
        assert key in qml, key
    assert "searchLimitsJson" in qml
    assert "loadSearchLimits" in qml
    assert 'text: "15"' not in qml
    assert 'text: "20000"' not in qml


def test_atomic_env_validates_before_writing(tmp_path):
    import pytest
    from app.cli.config_view import read_env, set_operational_config

    (tmp_path / ".env").write_text("MCP_PORT=18427\n", encoding="utf-8")
    before = (tmp_path / ".env").read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        set_operational_config(tmp_path, {"WORKSPACE_SEARCH_MAX_CONCURRENT": "0"})
    assert (tmp_path / ".env").read_text(encoding="utf-8") == before
    result = set_operational_config(
        tmp_path,
        {"WORKSPACE_SEARCH_MAX_CONCURRENT": "2", "SEARCH_TEXT_DEADLINE_SECONDS": "5"},
    )
    assert result["WORKSPACE_SEARCH_MAX_CONCURRENT"] == "2"
    assert float(read_env(tmp_path)["SEARCH_TEXT_DEADLINE_SECONDS"]) == 5.0


def test_fallback_regex_hostile_rejected(tmp_path, monkeypatch):
    import app.search_engines as engines

    monkeypatch.setattr(engines.config, "SEARCH_TEXT_DEADLINE_SECONDS", 5.0)
    monkeypatch.setattr(engines.config, "WORKSPACE_SEARCH_MAX_SCANNED_FILES", 10000)
    monkeypatch.setattr(engines.config, "WORKSPACE_SEARCH_MAX_SCANNED_BYTES", 10000000)
    started = time.monotonic()
    outcome = engines.run_python_search(
        root=tmp_path, query="(a+)+$", regex=True, case_sensitive=True,
        max_matches=10, include_hidden=False, max_work_matches=10000,
    )
    elapsed = time.monotonic() - started
    assert outcome.ok is False
    assert (outcome.error or {}).get("code") == "INVALID_ARGUMENT"
    assert elapsed < 2.0


def test_no_duplicate_journal_on_early_return(tmp_path, monkeypatch):
    import app.tools.workspace_search as search_module
    from app.tools.workspace_search import workspace_search

    _bind(tmp_path, monkeypatch)
    calls = {"count": 0}
    orig_finish = search_module._finish_workspace_journal

    def counting_finish(*args, **kwargs):
        calls["count"] += 1
        return orig_finish(*args, **kwargs)

    monkeypatch.setattr(search_module, "_finish_workspace_journal", counting_finish)
    result = search_module.workspace_search(query=None, path=str(tmp_path), mode="content")
    assert result["ok"] is False
    assert calls["count"] == 1
