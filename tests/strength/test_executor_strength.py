import time
from concurrent.futures import ThreadPoolExecutor

import pytest

import app.config
import app.host.executor as executor
from app.host.executor import CommandCapacity, execute_host_command


SIGTERM_IGNORING_CHILD = (
    "python3 -c \"import signal, time; "
    "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
    "signal.signal(signal.SIGINT, signal.SIG_IGN); "
    "print('ready', flush=True); time.sleep(60)\""
)


def test_huge_stdout_is_truncated_without_deadlock(isolated_workspace, monkeypatch):
    monkeypatch.setattr(app.config, "MAX_OUTPUT_BYTES", 4096)
    command = "python3 -c \"import sys; sys.stdout.write('A' * 100000)\""
    result = execute_host_command(command, timeout_seconds=30)
    assert result["ok"] is True
    assert result["stdout_truncated"] is True
    assert len(result["stdout"]) <= 4096 + 64
    assert result["stdout"].endswith("... [TRUNCATED]")


def test_sigterm_ignoring_child_is_escalated_and_reaped(isolated_workspace):
    started = time.monotonic()
    result = execute_host_command(SIGTERM_IGNORING_CHILD, timeout_seconds=2)
    elapsed = time.monotonic() - started
    assert result["ok"] is False
    assert result["error"]["code"] == "TIMEOUT"
    assert result["exit_code"] != 0
    assert elapsed < 15


def test_command_churn_leaves_capacity_clean(isolated_workspace, monkeypatch):
    capacity = CommandCapacity(max_concurrent=4, queue_timeout_seconds=10)
    monkeypatch.setattr(executor, "command_capacity", capacity)

    for index in range(40):
        result = execute_host_command("printf ok", timeout_seconds=15)
        assert result["ok"] is True, f"iteration {index}: {result}"

    stats = capacity.get_stats()
    assert stats["active"] == 0
    assert stats["queued"] == 0
    assert stats["started"] == 40
    assert stats["peak_active"] >= 1


def test_concurrent_commands_never_exceed_capacity(isolated_workspace, monkeypatch):
    capacity = CommandCapacity(max_concurrent=8, queue_timeout_seconds=20)
    monkeypatch.setattr(executor, "command_capacity", capacity)

    def run(index: int) -> dict:
        return execute_host_command(
            "python3 -c \"import time; time.sleep(0.25)\"",
            timeout_seconds=20,
        )

    with ThreadPoolExecutor(max_workers=32) as pool:
        futures = [pool.submit(run, index) for index in range(32)]
        results = [future.result(timeout=60) for future in futures]

    assert all(result["ok"] is True for result in results)
    stats = capacity.get_stats()
    assert stats["started"] == 32
    assert stats["active"] == 0
    assert stats["queued"] == 0
    assert 1 < stats["peak_active"] <= 8


def test_invalid_inputs_do_not_leak_capacity_slots(isolated_workspace, monkeypatch):
    capacity = CommandCapacity(max_concurrent=2, queue_timeout_seconds=5)
    monkeypatch.setattr(executor, "command_capacity", capacity)

    with pytest.raises(ValueError):
        execute_host_command("printf x", timeout_seconds=-1)

    with pytest.raises(TypeError):
        execute_host_command("printf x", timeout_seconds="2")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        execute_host_command("printf x", timeout_seconds=app.config.MAX_TIMEOUT_SECONDS + 1)
    with pytest.raises(PermissionError):
        execute_host_command("sudo id", timeout_seconds=5)

    with pytest.raises(PermissionError):
        execute_host_command("shutdown now", timeout_seconds=5)

    result = execute_host_command("printf recovered", timeout_seconds=10)
    assert result["ok"] is True

    stats = capacity.get_stats()
    assert stats["active"] == 0
    assert stats["rejected"] == 0
