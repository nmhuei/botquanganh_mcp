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


def test_host_knowledge_reads_guides_and_detects_tools(monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(app.config, "HOST_KNOWLEDGE_DIR", repo_root / "knowledge")

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
