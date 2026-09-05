import inspect
from pathlib import Path

import pytest

import app.config
from app.host.executor import execute_host_command
from app.host.files import (
    append_text_file,
    list_directory,
    read_text_file,
    replace_text_in_file,
    search_text,
    write_text_file,
)
from app.host.inventory import get_tool_inventory, read_guides
from app.host.policy import inspect_host_command
from app.tools.host import host_run_command, host_write_file
from app.tools.host_knowledge import host_knowledge


@pytest.fixture
def host_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(app.config, "HOST_RESTRICT_TO_WORKSPACE", True)
    monkeypatch.setattr(app.config, "HOST_COMMAND_POLICY", "guarded")
    monkeypatch.setattr(app.config, "HOST_INHERIT_ENV", True)
    monkeypatch.setattr(app.config, "MAX_OUTPUT_BYTES", 10_000)
    monkeypatch.setattr(app.config, "MAX_SINGLE_FILE_BYTES", 100_000)
    monkeypatch.setattr(app.config, "MAX_TIMEOUT_SECONDS", 10)
    monkeypatch.setattr(app.config, "ATTRIBUTION_MODE", "off")
    return tmp_path


def test_host_file_lifecycle(host_workspace):
    written = write_text_file("project/note.txt", "hello\nworld\n")
    assert written["ok"] is True
    assert (host_workspace / "project" / "note.txt").exists()

    listed = list_directory("project")
    assert [item["name"] for item in listed["items"]] == ["note.txt"]

    read = read_text_file("project/note.txt", start_line=2, end_line=2)
    assert read["content"] == "world"

    replaced = replace_text_in_file("project/note.txt", "world", "host")
    assert replaced["replacement_count"] == 1

    appended = append_text_file("project/note.txt", "\nready\n")
    assert appended["ok"] is True

    searched = search_text("ready", path="project")
    assert searched["results"][0]["path"] == "project/note.txt"


def test_host_path_cannot_escape_workspace(host_workspace):
    result = read_text_file
    with pytest.raises(PermissionError):
        result("../outside.txt")


def test_host_command_has_no_approval_parameter():
    assert "approval" not in inspect.signature(host_run_command).parameters


def test_host_mcp_command_marks_result_for_the_local_activity_journal(monkeypatch):
    monkeypatch.setattr(app.config, "ATTRIBUTION_MODE", "off")
    calls = []
    monkeypatch.setattr(
        "app.tools.host.execute_host_command",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"ok": True},
    )

    assert host_run_command("printf ok", timeout_seconds=5, cwd=".") == {"ok": True}
    assert calls == [
        (
            ("printf ok",),
            {
                "cwd": ".",
                "timeout_seconds": 5,
                "activity_source": "mcp",
                "activity_chat_id": None,
            },
        )
    ]


def test_guarded_policy_blocks_privilege_and_root_destruction(host_workspace):
    sudo = inspect_host_command("sudo apt update")
    assert sudo["allowed"] is False
    assert sudo["rule"] == "privilege_escalation"

    remove = inspect_host_command("rm -rf /")
    assert remove["allowed"] is False
    assert remove["severity"] == "forbidden"


def test_host_command_executes_on_configured_workspace(host_workspace):
    result = execute_host_command(
        "python3 -c \"from pathlib import Path; Path('made.txt').write_text('ok'); print('done')\"",
        timeout_seconds=5,
    )
    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["stdout"].strip() == "done"
    assert (host_workspace / "made.txt").read_text() == "ok"


def test_host_command_bounds_output(host_workspace, monkeypatch):
    monkeypatch.setattr(app.config, "MAX_OUTPUT_BYTES", 20)
    result = execute_host_command(
        "python3 -c \"print('x' * 200)\"",
        timeout_seconds=5,
    )
    assert result["ok"] is True
    assert result["stdout_truncated"] is True
    assert result["stdout"].endswith("... [TRUNCATED]")


def test_allowlist_policy_rejects_unknown_command(host_workspace, monkeypatch):
    monkeypatch.setattr(app.config, "HOST_COMMAND_POLICY", "allowlist")
    monkeypatch.setattr(app.config, "HOST_ALLOWED_COMMANDS", [])
    result = inspect_host_command("definitely-not-a-real-command --flag")
    assert result["allowed"] is False
    assert result["rule"] == "command_not_allowlisted"


def test_allowlist_policy_permits_all_when_configured_all(host_workspace, monkeypatch):
    monkeypatch.setattr(app.config, "HOST_COMMAND_POLICY", "allowlist")
    monkeypatch.setattr(app.config, "HOST_ALLOWED_COMMANDS", ["all"])
    result = inspect_host_command("custom-tool-123 --flag")
    assert result["allowed"] is True


def test_host_knowledge_reads_guides_and_detects_tools(monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(app.config, "HOST_KNOWLEDGE_DIR", repo_root / "knowledge")
    monkeypatch.setattr(app.config, "ATTRIBUTION_MODE", "off")

    guides = read_guides()
    assert guides["document_count"] >= 2
    assert any(doc["name"] == "WORKING_GUIDE.md" for doc in guides["documents"])

    inventory = get_tool_inventory(query="git", available_only=True, refresh=True)
    assert any(tool["name"] == "git" for tool in inventory["tools"])

    response = host_knowledge(section="tools", query="python", refresh=True)
    assert response["ok"] is True
    assert response["section"] == "tools"
    assert response["inventory"]["summary"]["returned"] >= 1


def test_command_parser_preserves_quoted_shell_separators(host_workspace):
    quoted = inspect_host_command(
        'python3 -c "from pathlib import Path; print(Path.cwd())"'
    )
    assert quoted["allowed"] is True
    assert quoted["command_names"] == ["python3"]

    chained = inspect_host_command("printf one && python3 -c 'print(\"a|b;c\")'")
    assert chained["command_names"] == ["printf", "python3"]


def test_host_write_existing_file_returns_file_exists_error(host_workspace):
    write_text_file("existing.txt", "one")
    result = host_write_file("existing.txt", "two", overwrite=False)
    assert result["ok"] is False
    assert result["error"]["code"] == "FILE_EXISTS"


def test_policy_splits_background_chains(host_workspace):
    result = inspect_host_command("printf one & python3 -c 'print(2)'")
    assert result["command_names"] == ["printf", "python3"]


def test_allowlist_rejects_dynamic_shell_substitution(host_workspace, monkeypatch):
    monkeypatch.setattr(app.config, "HOST_COMMAND_POLICY", "allowlist")
    monkeypatch.setattr(app.config, "HOST_ALLOWED_COMMANDS", [])
    result = inspect_host_command("printf '%s' $(whoami)")
    assert result["allowed"] is False
    assert result["rule"] == "dynamic_shell_not_allowlisted"


def test_guarded_policy_blocks_nested_and_alternative_privilege_tools(host_workspace):
    for command in ("echo $(sudo id)", "doas id", "pkexec id"):
        result = inspect_host_command(command)
        assert result["allowed"] is False, command
        assert result["rule"] == "privilege_escalation"


def test_host_tool_journal_start_is_visible_before_execution_and_result_is_self_describing(
    monkeypatch, tmp_path
):
    from app.chat_workspace import WorkspaceManager
    from app.tools.host import host_read_file

    chat_root = tmp_path / "chat-root"
    monkeypatch.setattr(app.config, "HOST_CHAT_WORKSPACES", True, raising=False)
    monkeypatch.setattr(app.config, "HOST_CHAT_ROOT", chat_root, raising=False)
    monkeypatch.setattr(app.config, "HOST_CHAT_QUOTA_MB", 16, raising=False)
    monkeypatch.setattr(app.config, "HOST_CHAT_JOURNAL_MAX_BYTES", 1_000_000, raising=False)
    WorkspaceManager(chat_root).create_or_bind("journal-live")

    seen = {}

    def fake_read(*_args, **_kwargs):
        during = WorkspaceManager(chat_root).read_events("journal-live")
        assert len(during) == 1
        assert during[0]["operation_phase"] == "started"
        assert during[0]["event_action"] == "host_read_file"
        seen["op"] = during[0]["op"]
        return {"ok": True, "content": "hello"}

    monkeypatch.setattr("app.tools.host.read_text_file", fake_read)

    assert host_read_file("README.md", chat_id="journal-live")["ok"] is True
    events = WorkspaceManager(chat_root).read_events("journal-live")
    assert [event["operation_phase"] for event in events] == ["started", "result"]
    assert events[1]["op"] == seen["op"]
    assert events[1]["kind"] == "host_read_file"
    assert events[1]["event_action"] == "host_read_file"
    assert events[1]["event_category"] == "file"
    assert events[1]["event_outcome"] == "success"



def test_host_run_command_never_persists_raw_secret_in_workspace_journal(
    monkeypatch, tmp_path
):
    from app.chat_workspace import WorkspaceManager

    chat_root = tmp_path / "chat-root"
    monkeypatch.setattr(app.config, "HOST_CHAT_WORKSPACES", True, raising=False)
    monkeypatch.setattr(app.config, "HOST_CHAT_ROOT", chat_root, raising=False)
    monkeypatch.setattr(app.config, "HOST_CHAT_QUOTA_MB", 16, raising=False)
    monkeypatch.setattr(app.config, "HOST_CHAT_JOURNAL_MAX_BYTES", 1_000_000, raising=False)
    WorkspaceManager(chat_root).create_or_bind("journal-secret")

    monkeypatch.setattr(
        "app.tools.host.execute_host_command",
        lambda *_args, **_kwargs: {
            "ok": True,
            "exit_code": 0,
            "stdout": "ok",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "output_incomplete": False,
        },
    )

    secret = "super-secret-value"
    result = host_run_command(
        f"GATEWAY_TOKEN={secret} printf ok",
        chat_id="journal-secret",
    )
    assert result["ok"] is True

    raw = (chat_root / "journal-secret" / "journal.jsonl").read_text(encoding="utf-8")
    assert secret not in raw
    assert "<redacted>" in raw
    events = WorkspaceManager(chat_root).read_events("journal-secret")
    assert [event["operation_phase"] for event in events] == ["started", "result"]
    assert events[0]["event_category"] == "process"
    assert events[1]["event_outcome"] == "success"


def test_host_run_command_reuses_the_workspace_journal_operation_for_activity(
    monkeypatch, tmp_path
):
    from app.chat_workspace import WorkspaceManager

    chat_root = tmp_path / "chat-root"
    monkeypatch.setattr(app.config, "HOST_CHAT_WORKSPACES", True, raising=False)
    monkeypatch.setattr(app.config, "HOST_CHAT_ROOT", chat_root, raising=False)
    monkeypatch.setattr(app.config, "HOST_CHAT_QUOTA_MB", 16, raising=False)
    monkeypatch.setattr(app.config, "HOST_CHAT_JOURNAL_MAX_BYTES", 1_000_000, raising=False)
    WorkspaceManager(chat_root).create_or_bind("journal-shared-op")
    calls = []
    monkeypatch.setattr(
        "app.tools.host.execute_host_command",
        lambda *_args, **kwargs: calls.append(kwargs) or {
            "ok": True,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "output_incomplete": False,
        },
    )

    assert host_run_command("pwd", chat_id="journal-shared-op")["ok"] is True

    journal_operation = WorkspaceManager(chat_root).read_events("journal-shared-op")[0]["op"]
    assert calls[0]["activity_operation_id"] == journal_operation
