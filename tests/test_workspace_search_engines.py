"""Engine limit and secure traversal tests (Task 3, RED)."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def test_ripgrep_deadline_terminates_and_reaps_process(monkeypatch):
    import app.search_engines as engines
    from app.search_models import SearchLimitReason

    class FakeStdout:
        def __init__(self):
            self.closed = False

        def readline(self):
            # Simulate a slow stream: first a match, then block.
            import time as _time

            _time.sleep(0.05)
            return ""

        def close(self):
            self.closed = True

    terminated = {"value": False}
    reaped = {"value": False}

    class FakeProcess:
        def __init__(self):
            self.pid = 999999
            self.stdout = FakeStdout()
            self.stderr = FakeStdout()
            self.returncode = None

        def wait(self, timeout=None):
            reaped["value"] = True
            return 0

        def kill(self):
            terminated["value"] = True

    def fake_popen(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(engines.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(engines.search_runtime, "terminate_process_group", lambda p: terminated.__setitem__("value", True))
    orig_reap = engines.search_runtime.reap_process

    def tracking_reap(proc, timeout_seconds=5.0):
        reaped["value"] = True
        return orig_reap(proc, timeout_seconds=timeout_seconds)

    monkeypatch.setattr(engines.search_runtime, "reap_process", tracking_reap)
    monkeypatch.setattr(engines.config, "SEARCH_TEXT_DEADLINE_SECONDS", 0.01)
    monkeypatch.setattr(
        engines, "_inventory_scan_bounds", lambda root, include_hidden, deadline: (0, 0, None)
    )

    outcome = engines.run_ripgrep_search(
        root=Path("."),
        query="needle",
        regex=False,
        case_sensitive=False,
        max_matches=10,
        include_hidden=False,
        max_work_matches=100000,
        exact_count=False,
    )
    assert outcome.limit_reason is SearchLimitReason.DEADLINE
    assert terminated["value"] is True
    assert reaped["value"] is True


def test_python_engine_skips_fifo_symlink_and_large_binary(tmp_path, monkeypatch):
    import app.search_engines as engines
    import app.config as config_module

    monkeypatch.setattr(config_module, "MAX_SINGLE_FILE_BYTES", 64)
    monkeypatch.setattr(config_module, "SEARCH_TEXT_DEADLINE_SECONDS", 30.0)
    monkeypatch.setattr(config_module, "WORKSPACE_SEARCH_MAX_SCANNED_FILES", 10000)
    monkeypatch.setattr(config_module, "WORKSPACE_SEARCH_MAX_SCANNED_BYTES", 10000000)
    monkeypatch.setattr(config_module, "WORKSPACE_SEARCH_MAX_WORK_MATCHES", 10000)
    monkeypatch.setattr(config_module, "WORKSPACE_SEARCH_MAX_LINE_CHARS", 8192)

    real_file = tmp_path / "real.txt"
    real_file.write_text("nothing here\n", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(real_file)
    except OSError:
        pass
    fifo = tmp_path / "pipe.fifo"
    try:
        os.mkfifo(fifo)
    except (OSError, AttributeError):
        pass
    big = tmp_path / "big.bin"
    big.write_bytes(b"\x00\x01\x02needle" + b"x" * 4096)
    denied_dir = tmp_path / "secrets"
    denied_dir.mkdir(exist_ok=True)
    (denied_dir / "hidden.txt").write_text("needle in denied\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "HOST_READ_DENY_GLOBS", ["secrets/*"])

    outcome = engines.run_python_search(
        root=tmp_path,
        query="needle",
        regex=False,
        case_sensitive=False,
        max_matches=10,
        include_hidden=False,
        max_work_matches=10000,
        exact_count=False,
    )
    assert outcome.matches == []
    assert outcome.counters.skipped_special_files >= 1
