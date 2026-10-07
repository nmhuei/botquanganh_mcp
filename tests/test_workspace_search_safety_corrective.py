"""Safety corrective pass: per-line budgets, safe regex, payload, finite, reap."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


def _hermetic_config(monkeypatch, tmp_path):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "off")


def test_python_dense_file_respects_work_budget_inside_file(tmp_path, monkeypatch):
    import app.config as config_module
    import app.search_engines as engines
    from app.search_models import SearchLimitReason

    fixture = tmp_path / "dense"
    fixture.mkdir()
    (fixture / "dense.txt").write_text("needle\n" * 5000, encoding="utf-8")
    monkeypatch.setattr(config_module, "WORKSPACE_SEARCH_MAX_SCANNED_FILES", 100)
    monkeypatch.setattr(config_module, "WORKSPACE_SEARCH_MAX_SCANNED_BYTES", 10000000)
    monkeypatch.setattr(config_module, "SEARCH_TEXT_DEADLINE_SECONDS", 15.0)
    monkeypatch.setattr(config_module, "MAX_SINGLE_FILE_BYTES", 10000000)

    outcome = engines.run_python_search(
        root=fixture, query="needle", regex=False, case_sensitive=False,
        max_matches=5000, include_hidden=False, max_work_matches=10,
    )
    assert outcome.limit_reason is SearchLimitReason.WORK_MATCHES
    assert outcome.total_found == 10
    assert len(outcome.matches) <= 10


def test_python_dense_file_respects_result_cap_inside_file(tmp_path, monkeypatch):
    import app.config as config_module
    import app.search_engines as engines
    from app.search_models import SearchLimitReason

    fixture = tmp_path / "dense_cap"
    fixture.mkdir()
    (fixture / "dense.txt").write_text("needle\n" * 5000, encoding="utf-8")
    monkeypatch.setattr(config_module, "WORKSPACE_SEARCH_MAX_SCANNED_FILES", 100)
    monkeypatch.setattr(config_module, "WORKSPACE_SEARCH_MAX_SCANNED_BYTES", 10000000)
    monkeypatch.setattr(config_module, "SEARCH_TEXT_DEADLINE_SECONDS", 15.0)
    monkeypatch.setattr(config_module, "MAX_SINGLE_FILE_BYTES", 10000000)

    outcome = engines.run_python_search(
        root=fixture, query="needle", regex=False, case_sensitive=False,
        max_matches=5, include_hidden=False, max_work_matches=100000,
    )
    assert outcome.limit_reason is SearchLimitReason.RESULT_CAP
    assert outcome.total_found == 6
    assert len(outcome.matches) == 5


def test_python_content_exact_result_cap_is_not_truncated(tmp_path, monkeypatch):
    import app.config as config_module
    import app.search_engines as engines

    fixture = tmp_path / "exact_cap"
    fixture.mkdir()
    (fixture / "exact.txt").write_text("needle\n" * 5, encoding="utf-8")
    monkeypatch.setattr(config_module, "WORKSPACE_SEARCH_MAX_SCANNED_FILES", 100)
    monkeypatch.setattr(config_module, "WORKSPACE_SEARCH_MAX_SCANNED_BYTES", 10000000)
    monkeypatch.setattr(config_module, "SEARCH_TEXT_DEADLINE_SECONDS", 15.0)
    monkeypatch.setattr(config_module, "MAX_SINGLE_FILE_BYTES", 10000000)

    outcome = engines.run_python_search(
        root=fixture, query="needle", regex=False, case_sensitive=False,
        max_matches=5, include_hidden=False, max_work_matches=100000,
    )
    assert outcome.count_complete is True
    assert outcome.limit_reason is None
    assert outcome.total_found == 5
    assert len(outcome.matches) == 5


def test_python_content_probes_one_match_past_cap(tmp_path, monkeypatch):
    import app.config as config_module
    import app.search_engines as engines
    from app.search_models import SearchLimitReason

    fixture = tmp_path / "over_cap"
    fixture.mkdir()
    (fixture / "over.txt").write_text("needle\n" * 6, encoding="utf-8")
    monkeypatch.setattr(config_module, "WORKSPACE_SEARCH_MAX_SCANNED_FILES", 100)
    monkeypatch.setattr(config_module, "WORKSPACE_SEARCH_MAX_SCANNED_BYTES", 10000000)
    monkeypatch.setattr(config_module, "SEARCH_TEXT_DEADLINE_SECONDS", 15.0)
    monkeypatch.setattr(config_module, "MAX_SINGLE_FILE_BYTES", 10000000)

    outcome = engines.run_python_search(
        root=fixture, query="needle", regex=False, case_sensitive=False,
        max_matches=5, include_hidden=False, max_work_matches=100000,
    )
    assert outcome.count_complete is False
    assert outcome.limit_reason is SearchLimitReason.RESULT_CAP
    assert outcome.total_found == 6
    assert len(outcome.matches) == 5


def test_python_byte_budget_enforced_while_reading(tmp_path, monkeypatch):
    import app.config as config_module
    import app.search_engines as engines
    from app.search_models import SearchLimitReason

    fixture = tmp_path / "bytes"
    fixture.mkdir()
    (fixture / "dense.txt").write_text("needle " + ("x" * 100) + "\n", encoding="utf-8")
    (fixture / "dense.txt").write_text(
        ("needle " + ("x" * 100) + "\n") * 200, encoding="utf-8"
    )
    monkeypatch.setattr(config_module, "WORKSPACE_SEARCH_MAX_SCANNED_FILES", 100)
    monkeypatch.setattr(config_module, "WORKSPACE_SEARCH_MAX_SCANNED_BYTES", 500)
    monkeypatch.setattr(config_module, "SEARCH_TEXT_DEADLINE_SECONDS", 15.0)
    monkeypatch.setattr(config_module, "MAX_SINGLE_FILE_BYTES", 1000000)

    outcome = engines.run_python_search(
        root=fixture, query="needle", regex=False, case_sensitive=False,
        max_matches=500, include_hidden=False, max_work_matches=100000,
    )
    assert outcome.limit_reason is SearchLimitReason.SCANNED_BYTES
    assert outcome.counters.scanned_bytes <= 500


def test_python_path_tracks_bytes_and_caps(tmp_path, monkeypatch):
    import app.config as config_module
    import app.search_engines as engines
    from app.search_models import SearchLimitReason

    fixture = tmp_path / "ppath"
    fixture.mkdir()
    for index in range(4):
        (fixture / f"f{index}.txt").write_bytes(b"x" * 100)
    monkeypatch.setattr(config_module, "WORKSPACE_SEARCH_MAX_SCANNED_FILES", 100)
    monkeypatch.setattr(config_module, "WORKSPACE_SEARCH_MAX_SCANNED_BYTES", 150)
    monkeypatch.setattr(config_module, "SEARCH_TEXT_DEADLINE_SECONDS", 15.0)

    outcome = engines.run_python_path_search(
        root=fixture, glob_pattern="*", include_hidden=False, max_matches=100,
    )
    assert outcome.limit_reason is SearchLimitReason.SCANNED_BYTES
    assert outcome.counters.scanned_files == 1
    assert outcome.counters.scanned_bytes == 100
    assert outcome.counters.scanned_bytes <= 150


def test_ripgrep_path_counters_include_inventory_bytes(tmp_path, monkeypatch):
    import app.search_engines as engines

    monkeypatch.setattr(engines.config, "SEARCH_TEXT_DEADLINE_SECONDS", 5.0)
    monkeypatch.setattr(engines.config, "WORKSPACE_SEARCH_MAX_SCANNED_FILES", 100)
    monkeypatch.setattr(engines.config, "WORKSPACE_SEARCH_MAX_SCANNED_BYTES", 1000000)

    class FakeStdout:
        def __iter__(self):
            yield "/tmp/a.txt\n"

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

    monkeypatch.setattr(engines.subprocess, "Popen", lambda *a, **k: FakeProcess())
    monkeypatch.setattr(
        engines, "_inventory_scan_bounds", lambda root, include_hidden, deadline: (3, 300, None)
    )
    outcome = engines.run_ripgrep_path_search(
        root=Path("."), glob_pattern="*", include_hidden=False, max_matches=10,
    )
    assert outcome.counters.scanned_bytes == 300
    assert outcome.counters.scanned_files >= 1


def test_safe_subset_rejects_bypass_with_repeated_quantifiers(tmp_path, monkeypatch):
    import app.search_engines as engines

    monkeypatch.setattr(engines.config, "SEARCH_TEXT_DEADLINE_SECONDS", 5.0)
    monkeypatch.setattr(engines.config, "WORKSPACE_SEARCH_MAX_SCANNED_FILES", 100)
    monkeypatch.setattr(engines.config, "WORKSPACE_SEARCH_MAX_SCANNED_BYTES", 1000000)
    # Old two-pattern heuristic accepts this (no parens), new subset rejects.
    bypass = "a*a*a*a*b"
    started = time.monotonic()
    outcome = engines.run_python_search(
        root=tmp_path, query=bypass, regex=True, case_sensitive=True,
        max_matches=10, include_hidden=False, max_work_matches=10000,
    )
    elapsed = time.monotonic() - started
    assert outcome.ok is False
    assert (outcome.error or {}).get("code") == "INVALID_ARGUMENT"
    assert elapsed < 2.0


def test_safe_subset_accepts_single_quantifier(tmp_path, monkeypatch):
    import app.search_engines as engines

    monkeypatch.setattr(engines.config, "SEARCH_TEXT_DEADLINE_SECONDS", 5.0)
    monkeypatch.setattr(engines.config, "WORKSPACE_SEARCH_MAX_SCANNED_FILES", 100)
    monkeypatch.setattr(engines.config, "WORKSPACE_SEARCH_MAX_SCANNED_BYTES", 1000000)
    monkeypatch.setattr(engines.config, "MAX_SINGLE_FILE_BYTES", 1000000)
    (tmp_path / "s.txt").write_text("secret_value\n", encoding="utf-8")
    outcome = engines.run_python_search(
        root=tmp_path, query=r"secret_\w+", regex=True, case_sensitive=True,
        max_matches=10, include_hidden=False, max_work_matches=10000,
    )
    assert outcome.ok is True
    assert outcome.total_found == 1


def test_safe_subset_rejects_groups_and_alternation(tmp_path, monkeypatch):
    import app.search_engines as engines

    monkeypatch.setattr(engines.config, "SEARCH_TEXT_DEADLINE_SECONDS", 5.0)
    for hostile in ("(a+)+$", "(a|aa)+", "(a.*b)+", "((a+)+)"):
        outcome = engines.run_python_search(
            root=tmp_path, query=hostile, regex=True, case_sensitive=True,
            max_matches=10, include_hidden=False, max_work_matches=10000,
        )
        assert outcome.ok is False, hostile


def test_safe_subset_rejects_many_optional_quantifiers(tmp_path, monkeypatch):
    import app.search_engines as engines

    monkeypatch.setattr(engines.config, "SEARCH_TEXT_DEADLINE_SECONDS", 5.0)
    monkeypatch.setattr(engines.config, "WORKSPACE_SEARCH_MAX_SCANNED_FILES", 100)
    monkeypatch.setattr(engines.config, "WORKSPACE_SEARCH_MAX_SCANNED_BYTES", 1000000)
    hostile = "a?" * 40 + "b"
    outcome = engines.run_python_search(
        root=tmp_path, query=hostile, regex=True, case_sensitive=True,
        max_matches=10, include_hidden=False, max_work_matches=10000,
    )
    assert outcome.ok is False
    assert (outcome.error or {}).get("code") == "INVALID_ARGUMENT"


def test_payload_budget_has_no_floor_and_fallback_fits_low_ceiling(monkeypatch):
    import json as json_module
    from app import tools_common

    monkeypatch.setattr("app.config.MCP_MAX_PAYLOAD_BYTES", 1500)
    monkeypatch.setattr("app.config.MCP_TOOL_RESULT_OVERHEAD_BYTES", 500)
    assert tools_common.search_response_budget() == 1000
    payload = {"ok": True, "data": "x" * 5000}
    bounded = tools_common.enforce_bridge_payload_limit(payload, tool_name="workspace_search")
    assert bounded["ok"] is False
    assert bounded["limit_bytes"] == 1500
    blob = json_module.dumps(bounded, ensure_ascii=False)
    assert "512KB" not in blob
    assert "4096" not in blob
    assert len(blob.encode("utf-8")) <= 1500


def test_payload_fallback_fits_minimal_ceiling_high_overhead(monkeypatch):
    import json as json_module
    from app import tools_common

    monkeypatch.setattr("app.config.MCP_MAX_PAYLOAD_BYTES", 1024)
    monkeypatch.setattr("app.config.MCP_TOOL_RESULT_OVERHEAD_BYTES", 1000)
    assert tools_common.search_response_budget() == 24
    payload = {"ok": True, "data": "y" * 5000}
    bounded = tools_common.enforce_bridge_payload_limit(payload, tool_name="workspace_search")
    encoded = json_module.dumps(bounded, ensure_ascii=False).encode("utf-8")
    assert len(encoded) <= 1024
    assert bounded["ok"] is False


def test_config_rejects_non_finite_floats():
    from app.cli.config_view import _parse_float

    valid, _ = _parse_float("inf", 0.0, None)
    assert valid is False
    valid, _ = _parse_float("nan", 0.0, None)
    assert valid is False
    valid, _ = _parse_float("-inf", 0.0, None)
    assert valid is False


def test_config_env_rejects_non_finite(monkeypatch):
    import subprocess
    import sys

    for key, bad in (
        ("SEARCH_TEXT_DEADLINE_SECONDS", "nan"),
        ("SEARCH_TEXT_DEADLINE_SECONDS", "inf"),
        ("WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS", "nan"),
        ("WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS", "infinity"),
    ):
        monkeypatch.setenv(key, bad)
        proc = subprocess.run(
            [sys.executable, "-c", "import app.config"],
            capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode != 0, key
        assert key in proc.stderr
        monkeypatch.delenv(key, raising=False)


def test_overhead_above_ceiling_rejected_at_startup(monkeypatch):
    import subprocess
    import sys

    monkeypatch.setenv("MCP_MAX_PAYLOAD_BYTES", "1024")
    monkeypatch.setenv("MCP_TOOL_RESULT_OVERHEAD_BYTES", "2048")
    proc = subprocess.run(
        [sys.executable, "-c", "import app.config"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode != 0
    assert "MCP_TOOL_RESULT_OVERHEAD_BYTES" in proc.stderr


def test_reap_kills_after_grace_expiry():
    from app import search_runtime as runtime

    calls = {"kill": 0, "waits": 0}

    class FakeProc:
        stdout = None
        stderr = None

        def wait(self, timeout=None):
            calls["waits"] += 1
            if calls["waits"] == 1:
                import subprocess as _sp

                raise _sp.TimeoutExpired(cmd="rg", timeout=timeout)
            return 0

        def poll(self):
            return None

        def kill(self):
            calls["kill"] += 1

    runtime.reap_process(FakeProc(), timeout_seconds=0.01)
    assert calls["kill"] >= 1
    assert calls["waits"] >= 2


def test_ripgrep_silent_stdout_sustained_stderr_deadline_reaps(monkeypatch):
    import app.search_engines as engines
    from app.search_models import SearchLimitReason

    read_fd, _write_fd = os.pipe()
    terminated = {"value": False}
    reaped = {"value": False}

    class FakeStdout:
        def fileno(self):
            return read_fd

        def close(self):
            return None

    class FakeStderr:
        def read(self, *args, **kwargs):
            size = args[0] if args else 1024
            time.sleep(0.005)
            return "e" * min(int(size), 512)

    class FakeProcess:
        stdout = FakeStdout()
        stderr = FakeStderr()
        returncode = None
        pid = 999997

        def poll(self):
            return None

        def wait(self, timeout=None):
            reaped["value"] = True
            return 0

        def kill(self):
            terminated["value"] = True

    created = {}

    def fake_popen(*args, **kwargs):
        proc = FakeProcess()
        created["proc"] = proc
        return proc

    monkeypatch.setattr(engines.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        engines.search_runtime, "terminate_process_group",
        lambda p: terminated.__setitem__("value", True),
    )
    orig_reap = engines.search_runtime.reap_process

    def tracking_reap(proc, timeout_seconds=None):
        reaped["value"] = True
        terminated["value"] = True
        return orig_reap(proc, timeout_seconds=timeout_seconds)

    monkeypatch.setattr(engines.search_runtime, "reap_process", tracking_reap)
    monkeypatch.setattr(engines.config, "SEARCH_TEXT_DEADLINE_SECONDS", 0.05)
    monkeypatch.setattr(engines.config, "WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(engines.config, "HOST_TASK_KILL_GRACE_SECONDS", 0.05)
    monkeypatch.setattr(
        engines, "_inventory_scan_bounds", lambda root, include_hidden, deadline: (0, 0, None)
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
            os.close(_write_fd)
        except OSError:
            pass
    assert outcome.limit_reason is SearchLimitReason.DEADLINE
    assert terminated["value"] is True
    assert reaped["value"] is True
    assert elapsed < 2.0
