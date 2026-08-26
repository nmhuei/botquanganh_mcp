import json
import stat

import app.activity_log as activity
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
