import json
import stat
import threading
import time

import app.activity_log as activity
import app.config
import app.host.executor as executor


def test_records_and_reads_mcp_command_output_with_secret_redaction(tmp_path, monkeypatch):
    journal = tmp_path / "mcp_command_activity.jsonl"
    monkeypatch.setattr(activity, "MCP_COMMAND_ACTIVITY_LOG", journal)

    activity.record_mcp_command_activity(
        command="printf 'token=super-secret'",
        cwd="/workspace",
        result={
            "ok": True,
            "exit_code": 0,
            "duration_ms": 8,
            "stdout": "Bearer abc.def.ghi\nfinished",
            "stderr": "",
        },
    )

    records = activity.read_mcp_command_activity()
    assert len(records) == 1
    assert records[0]["tool"] == "host_run_command"
    assert records[0]["exit_code"] == 0
    assert "super-secret" not in records[0]["command"]
    assert "abc.def.ghi" not in records[0]["stdout"]
    assert stat.S_IMODE(journal.stat().st_mode) == 0o600


def test_activity_record_keeps_the_optional_workplace_id(tmp_path, monkeypatch):
    journal = tmp_path / "mcp_command_activity.jsonl"
    monkeypatch.setattr(activity, "MCP_COMMAND_ACTIVITY_LOG", journal)

    activity.record_mcp_command_activity(
        command="printf ok",
        cwd="/workspace",
        chat_id="chat-alpha",
        result={"ok": True, "stdout": "ok"},
    )

    assert activity.read_mcp_command_activity()[0]["chat_id"] == "chat-alpha"


def test_activity_record_keeps_optional_lifecycle_fields(tmp_path, monkeypatch):
    journal = tmp_path / "mcp_command_activity.jsonl"
    monkeypatch.setattr(activity, "MCP_COMMAND_ACTIVITY_LOG", journal)

    activity.record_mcp_command_activity(
        command="sleep 10",
        cwd="/workspace",
        chat_id="chat-alpha",
        operation_id="act-123",
        phase="started",
        status="running",
        result={"ok": False},
    )

    record = activity.read_mcp_command_activity()[0]
    assert record["operation_id"] == "act-123"
    assert record["phase"] == "started"
    assert record["status"] == "running"


def test_activity_record_preserves_large_output_for_desktop_ui(tmp_path, monkeypatch):
    journal = tmp_path / "mcp_command_activity.jsonl"
    monkeypatch.setattr(activity, "MCP_COMMAND_ACTIVITY_LOG", journal)
    stdout = "A" * 20_000 + " token=super-secret"
    stderr = "B" * 20_000

    activity.record_mcp_command_activity(
        command="python3 report.py",
        cwd="/workspace",
        result={"ok": True, "stdout": stdout, "stderr": stderr},
    )

    record = activity.read_mcp_command_activity()[0]

    assert record["stdout"] == "A" * 20_000 + " token=[REDACTED]"
    assert record["stderr"] == stderr
    assert record["stdout_truncated"] is False
    assert record["stderr_truncated"] is False


def test_activity_rotation_keeps_the_newest_complete_output(tmp_path, monkeypatch):
    journal = tmp_path / "mcp_command_activity.jsonl"
    monkeypatch.setattr(activity, "MCP_COMMAND_ACTIVITY_LOG", journal)
    monkeypatch.setattr(activity, "_MAX_ACTIVITY_OUTPUT_BYTES", 200)

    activity.record_mcp_command_activity(
        command="first",
        cwd="/workspace",
        result={"ok": True, "stdout": "A" * 120},
    )
    activity.record_mcp_command_activity(
        command="second",
        cwd="/workspace",
        result={"ok": True, "stdout": "B" * 120},
    )

    records = activity.read_mcp_command_activity()

    assert [record["command"] for record in records] == ["second"]
    assert records[0]["stdout"] == "B" * 120


def test_activity_discards_an_attachment_when_its_journal_row_cannot_be_written(
    tmp_path, monkeypatch
):
    journal = tmp_path / "mcp_command_activity.jsonl"
    monkeypatch.setattr(activity, "MCP_COMMAND_ACTIVITY_LOG", journal)
    monkeypatch.setattr(activity, "_MAX_RECORD_BYTES", 1)

    activity.record_mcp_command_activity(
        command="report",
        cwd="/workspace",
        result={"ok": True, "stdout": "complete output"},
    )

    assert activity.read_mcp_command_activity() == []
    assert not (tmp_path / "mcp_command_activity_output").exists()


def test_activity_retries_a_short_journal_write(tmp_path, monkeypatch):
    journal = tmp_path / "mcp_command_activity.jsonl"
    monkeypatch.setattr(activity, "MCP_COMMAND_ACTIVITY_LOG", journal)
    original_write = activity.os.write

    def short_write(descriptor, data):
        length = max(1, len(data) // 2)
        return original_write(descriptor, data[:length])

    monkeypatch.setattr(activity.os, "write", short_write)

    activity.record_mcp_command_activity(
        command="report",
        cwd="/workspace",
        result={"ok": True, "stdout": "complete output"},
    )

    assert activity.read_mcp_command_activity()[0]["stdout"] == "complete output"


def test_activity_rolls_back_a_partial_journal_write_before_the_next_record(
    tmp_path, monkeypatch
):
    journal = tmp_path / "mcp_command_activity.jsonl"
    monkeypatch.setattr(activity, "MCP_COMMAND_ACTIVITY_LOG", journal)
    original_write = activity.os.write
    calls = 0

    def partially_then_fail(descriptor, data):
        nonlocal calls
        calls += 1
        if calls == 1:
            length = max(1, len(data) // 2)
            return original_write(descriptor, data[:length])
        raise OSError("disk full")

    monkeypatch.setattr(activity.os, "write", partially_then_fail)
    activity.record_mcp_command_activity(
        command="broken",
        cwd="/workspace",
        result={"ok": True, "stdout": "discarded"},
    )

    assert journal.read_text(encoding="utf-8") == ""
    monkeypatch.setattr(activity.os, "write", original_write)
    activity.record_mcp_command_activity(
        command="complete",
        cwd="/workspace",
        result={"ok": True, "stdout": "saved"},
    )

    records = activity.read_mcp_command_activity()
    assert [record["command"] for record in records] == ["complete"]


def test_reader_ignores_invalid_and_non_mcp_records(tmp_path, monkeypatch):
    journal = tmp_path / "mcp_command_activity.jsonl"
    monkeypatch.setattr(activity, "MCP_COMMAND_ACTIVITY_LOG", journal)
    journal.write_text(
        "not json\n"
        + json.dumps({"schema_version": 1, "source": "rest", "tool": "host_run_command"})
        + "\n"
        + json.dumps(
            {
                "schema_version": 1,
                "source": "mcp",
                "tool": "host_run_command",
                "event_id": "latest",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert [record["event_id"] for record in activity.read_mcp_command_activity()] == ["latest"]


def test_mcp_activity_records_a_command_rejected_before_execution(monkeypatch):
    records = []
    monkeypatch.setattr(
        executor,
        "_execute_host_command_impl",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("blocked")),
    )
    monkeypatch.setattr(
        executor,
        "record_mcp_command_activity",
        lambda **record: records.append(record),
    )

    try:
        executor.execute_host_command("blocked-command", activity_source="mcp")
    except PermissionError:
        pass
    else:  # pragma: no cover - documents the expected error path
        raise AssertionError("The test command should be blocked")

    assert records[0]["command"] == "blocked-command"
    assert records[0]["result"]["ok"] is False
    assert records[0]["result"]["stderr"] == "blocked"


def test_executor_records_running_then_terminal_for_mcp_command(monkeypatch):
    records = []

    def fake_execute(command, *, cwd, timeout_seconds, on_started=None):
        assert command == "sleep 10"
        assert cwd == "/workspace"
        assert timeout_seconds == 30
        assert on_started is not None
        on_started("/workspace")
        return {
            "ok": True,
            "cwd": "/workspace",
            "exit_code": 0,
            "stdout": "done",
            "stderr": "",
            "duration_ms": 10,
        }

    monkeypatch.setattr(executor, "_execute_host_command_impl", fake_execute)
    monkeypatch.setattr(
        executor,
        "record_mcp_command_activity",
        lambda **record: records.append(record),
    )

    result = executor.execute_host_command(
        "sleep 10",
        cwd="/workspace",
        activity_source="mcp",
        activity_chat_id="chat-alpha",
    )

    assert result["ok"] is True
    assert [record["phase"] for record in records] == ["started", "completed"]
    assert [record["status"] for record in records] == ["running", "succeeded"]
    assert records[0]["operation_id"] == records[1]["operation_id"]
    assert records[0]["chat_id"] == "chat-alpha"


def test_executor_journals_running_before_a_real_mcp_command_finishes(tmp_path, monkeypatch):
    journal = tmp_path / "mcp_command_activity.jsonl"
    monkeypatch.setattr(activity, "MCP_COMMAND_ACTIVITY_LOG", journal)
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(app.config, "HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr(app.config, "HOST_READ_SCOPE_SET", False)
    monkeypatch.setattr(app.config, "HOST_WRITE_SCOPE_SET", False)
    monkeypatch.setattr(app.config, "MAX_TIMEOUT_SECONDS", 5)
    outcome = []

    worker = threading.Thread(
        target=lambda: outcome.append(
            executor.execute_host_command(
                'python3 -c "import time; time.sleep(0.4)"',
                cwd=str(tmp_path),
                timeout_seconds=2,
                activity_source="mcp",
                activity_chat_id="chat-alpha",
            )
        )
    )
    worker.start()
    deadline = time.monotonic() + 2
    running_records = []
    while time.monotonic() < deadline:
        running_records = activity.read_mcp_command_activity()
        if any(record.get("status") == "running" for record in running_records):
            break
        time.sleep(0.02)

    assert worker.is_alive()
    assert len(running_records) == 1
    assert running_records[0]["status"] == "running"
    assert running_records[0]["phase"] == "started"
    assert running_records[0]["chat_id"] == "chat-alpha"

    worker.join(timeout=3)
    assert not worker.is_alive()
    assert outcome[0]["ok"] is True
    records = activity.read_mcp_command_activity()
    assert [record["status"] for record in records] == ["succeeded", "running"]
    assert records[0]["operation_id"] == records[1]["operation_id"]


def test_executor_returns_full_output_when_output_limit_is_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(app.config, "HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr(app.config, "HOST_READ_SCOPE_SET", False)
    monkeypatch.setattr(app.config, "HOST_WRITE_SCOPE_SET", False)
    monkeypatch.setattr(app.config, "MAX_OUTPUT_BYTES", 0)
    monkeypatch.setattr(app.config, "MAX_TIMEOUT_SECONDS", 5)

    result = executor.execute_host_command(
        "python3 -c \"import sys; sys.stdout.write('A' * 100000)\"",
        cwd=str(tmp_path),
        timeout_seconds=2,
    )

    assert result["ok"] is True
    assert result["stdout"] == "A" * 100_000
    assert result["stdout_truncated"] is False


def test_unlimited_output_waits_for_an_active_reader(tmp_path, monkeypatch):
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(app.config, "HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr(app.config, "HOST_READ_SCOPE_SET", False)
    monkeypatch.setattr(app.config, "HOST_WRITE_SCOPE_SET", False)
    monkeypatch.setattr(app.config, "MAX_OUTPUT_BYTES", 0)
    monkeypatch.setattr(app.config, "MAX_TIMEOUT_SECONDS", 10)

    def slowly_draining_reader(pipe, _max_bytes, result):
        try:
            pipe.read()
        finally:
            pipe.close()
        for _ in range(36):
            result["last_progress_at"] = time.monotonic()
            time.sleep(0.2)
        result.update(text="complete", truncated=False)

    monkeypatch.setattr(executor, "_drain_limited", slowly_draining_reader)

    result = executor.execute_host_command(
        "printf done", cwd=str(tmp_path), timeout_seconds=2
    )

    assert result["stdout"] == "complete"
    assert result["stderr"] == "complete"
    assert result["output_incomplete"] is False


def test_unlimited_output_waits_for_reader_conversion_after_eof(tmp_path, monkeypatch):
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(app.config, "HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr(app.config, "HOST_READ_SCOPE_SET", False)
    monkeypatch.setattr(app.config, "HOST_WRITE_SCOPE_SET", False)
    monkeypatch.setattr(app.config, "MAX_OUTPUT_BYTES", 0)
    monkeypatch.setattr(app.config, "MAX_TIMEOUT_SECONDS", 10)

    def reader_with_slow_conversion(pipe, _max_bytes, result):
        try:
            pipe.read()
        finally:
            pipe.close()
        result["eof_at"] = time.monotonic()
        time.sleep(2.2)
        result.update(text="complete", truncated=False)

    monkeypatch.setattr(executor, "_drain_limited", reader_with_slow_conversion)

    result = executor.execute_host_command(
        "printf done", cwd=str(tmp_path), timeout_seconds=2
    )

    assert result["stdout"] == "complete"
    assert result["stderr"] == "complete"
    assert result["output_incomplete"] is False


def test_executor_uses_the_workspace_operation_id_for_mcp_activity(monkeypatch):
    import app.host.executor as executor

    records = []

    def fake_execute(_command, *, cwd, timeout_seconds, on_started=None):
        assert cwd == "/workspace"
        assert timeout_seconds == 5
        assert on_started is not None
        on_started("/workspace")
        return {"ok": True, "stdout": "", "stderr": "", "duration_ms": 1}

    monkeypatch.setattr(executor, "_execute_host_command_impl", fake_execute)
    monkeypatch.setattr(
        executor,
        "record_mcp_command_activity",
        lambda **record: records.append(record),
    )

    executor.execute_host_command(
        "pwd",
        cwd="/workspace",
        timeout_seconds=5,
        activity_source="mcp",
        activity_chat_id="chat-a",
        activity_operation_id="op-shared",
    )

    assert [record["operation_id"] for record in records] == ["op-shared", "op-shared"]
