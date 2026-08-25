import subprocess
import threading

import app.config
import app.auth as auth_module
from app.auth import verify_token
from app.error_contract import classify_exception
from app.host.files import list_directory, replace_text_in_file
from app.host.policy import inspect_host_command
from app.metrics import MetricsTracker


def test_replace_text_roundtrip_content_is_exact(isolated_workspace):
    target = isolated_workspace / "notes.txt"
    target.write_text("hello world")
    result = replace_text_in_file(str(target), "world", "WORLD")
    assert result["ok"] is True
    assert result["replacement_count"] == 1
    assert target.read_text() == "hello WORLD"


def test_concurrent_disjoint_replaces_do_not_lose_updates(isolated_workspace):
    target = isolated_workspace / "shared.txt"
    target.write_text("alpha beta")
    barrier = threading.Barrier(2)

    def replace(old: str, new: str) -> None:
        barrier.wait(timeout=5)
        replace_text_in_file(str(target), old, new)

    threads = [
        threading.Thread(target=replace, args=("alpha", "ALPHA")),
        threading.Thread(target=replace, args=("beta", "BETA")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    final = set(target.read_text().split())
    assert final == {"ALPHA", "BETA"}, f"lost update detected: {final!r}"


def test_relative_recursive_rm_outside_workspace_is_blocked(isolated_workspace):
    result = inspect_host_command("rm -rf ../..")
    assert result["allowed"] is False
    assert result["rule"] == "recursive_remove_outside_workspace"


def test_uppercase_recursive_flag_is_detected(isolated_workspace):
    outside = isolated_workspace.parent / "victim"
    assert inspect_host_command(f"rm -Rf {outside}")["allowed"] is False


def test_recursive_rm_inside_workspace_stays_allowed(isolated_workspace):
    target = isolated_workspace / "sub"
    target.mkdir()
    assert inspect_host_command(f"rm -rf '{target}'")["allowed"] is True


def test_nonrecursive_long_options_are_not_flagged_recursive():
    for command in ("rm --verbose /tmp/x", "rm --dir /tmp/somedir"):
        result = inspect_host_command(command)
        assert result["allowed"] is True, f"{command} wrongly blocked: {result}"


def test_non_ascii_auth_token_does_not_raise(monkeypatch):
    monkeypatch.setattr(app.config, "REQUIRE_AUTH", True)
    monkeypatch.setattr(app.config, "GATEWAY_TOKEN", "mật-khẩu-123")
    monkeypatch.setattr(auth_module, "REQUIRE_AUTH", True)
    monkeypatch.setattr(auth_module, "GATEWAY_TOKEN", "mật-khẩu-123")
    assert verify_token("mật-khẩu-123") is True
    assert verify_token("sai-mật-khẩu") is False
    assert verify_token(None) is False


def test_subprocess_timeout_expires_maps_to_timeout_spec():
    spec = classify_exception(subprocess.TimeoutExpired(cmd="x", timeout=1))
    assert spec.code == "TIMEOUT"
    assert spec.http_status == 408


def test_metrics_path_counts_are_bounded():
    tracker = MetricsTracker()
    for index in range(1200):
        tracker.record_request(f"/path-{index}", 1.0)
    stats = tracker.get_stats()
    assert len(stats["path_counts"]) <= 512
    assert sum(stats["path_counts"].values()) == 1200


def test_detached_child_holding_pipes_reports_output_incomplete(isolated_workspace):
    import time

    from app.host.executor import execute_host_command

    started = time.monotonic()
    result = execute_host_command("setsid sleep 30 &", timeout_seconds=10)
    elapsed = time.monotonic() - started
    assert result["ok"] is True
    assert result["output_incomplete"] is True
    assert elapsed < 15


def test_list_directory_exact_capacity_is_not_truncated(isolated_workspace):
    for name in ("a.txt", "b.txt"):
        (isolated_workspace / name).write_text("x")
    exact = list_directory(str(isolated_workspace), max_entries=2)
    assert exact["truncated"] is False
    assert len(exact["items"]) == 2

    (isolated_workspace / "c.txt").write_text("x")
    over = list_directory(str(isolated_workspace), max_entries=2)
    assert over["truncated"] is True
    assert len(over["items"]) == 2
