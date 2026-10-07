import pytest
from pathlib import Path
from app.tools.terminal_execute import terminal_execute
from app.chat_workspace import WorkspaceManager


def test_terminal_execute_enforce_mode_requires_chat_id(monkeypatch):
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")
    res = terminal_execute(command="echo hi", chat_id=None)
    assert res["ok"] is False
    assert res["error"]["code"] == "E6"


def test_terminal_execute_basic_and_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")

    chat_id = "test-chat-term"
    mgr = WorkspaceManager(tmp_path)
    bind_res = mgr.create_or_bind(chat_id)

    # 1. Normal execution
    res1 = terminal_execute(
        command="echo 'BQA_MCP_V2_TEST'",
        cwd=str(bind_res.path),
        chat_id=chat_id,
    )
    assert res1["ok"] is True
    assert res1["exit_code"] == 0
    assert "BQA_MCP_V2_TEST" in res1["output"]

    # 2. Semantic error extraction
    res2 = terminal_execute(
        command="python3 -c 'raise KeyError(\"custom_error_key\")'",
        cwd=str(bind_res.path),
        chat_id=chat_id,
    )
    assert res2["ok"] is False
    assert res2["exit_code"] != 0
    assert any("KeyError" in err for err in res2["summary"]["errors"])

    # 3. Timeout process group kill
    res3 = terminal_execute(
        command="sleep 10",
        timeout_seconds=1,
        cwd=str(bind_res.path),
        chat_id=chat_id,
    )
    assert res3["ok"] is False
    assert res3["timed_out"] is True
    assert res3["exit_code"] == -9


def test_terminal_execute_result_has_ui_safe_command_summary(tmp_path, monkeypatch):
    from app.tools.terminal_execute import terminal_execute

    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")
    chat_id = "test-chat-summary"
    WorkspaceManager(tmp_path).create_or_bind(chat_id)

    result = terminal_execute(command="echo card-summary-test", chat_id=chat_id)
    assert result["command_summary"] == "echo card-summary-test"


def test_terminal_execute_output_cap_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")
    monkeypatch.setattr("app.tools.terminal_execute._MAX_OUTPUT_BYTES", 64)

    chat_id = "test-chat-output-cap"
    WorkspaceManager(tmp_path).create_or_bind(chat_id)

    result = terminal_execute(command="python3 -c 'print(\"x\" * 200)'", chat_id=chat_id)

    assert result["ok"] is True
    assert result["output_truncated"] is True
    assert "[TRUNCATED]" in result["output"]


def test_terminal_execute_timeout_invokes_process_group_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")

    killed = []
    monkeypatch.setattr("app.tools.terminal_execute._kill_process_group", lambda pid: killed.append(pid))

    chat_id = "test-chat-cleanup"
    WorkspaceManager(tmp_path).create_or_bind(chat_id)

    result = terminal_execute(command="sleep 5", timeout_seconds=1, chat_id=chat_id)

    assert result["timed_out"] is True
    assert result["exit_code"] == -9
    assert killed
    assert isinstance(killed[0], int)



def test_terminal_execute_timeout_uses_cleanup_with_mock_process(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")

    class FakeProcess:
        pid = 4321
        returncode = 0

        def communicate(self, timeout=None):
            if timeout != 2.0:
                import subprocess
                raise subprocess.TimeoutExpired("fake", timeout)
            self.returncode = -9
            return "", ""

    cleanup = []
    monkeypatch.setattr("app.tools.terminal_execute.subprocess.Popen", lambda *a, **k: FakeProcess())
    monkeypatch.setattr("app.tools.terminal_execute._kill_process_group", lambda pid: cleanup.append(pid))

    chat_id = "test-chat-mock-timeout"
    WorkspaceManager(tmp_path).create_or_bind(chat_id)

    result = terminal_execute(command="echo ignored", timeout_seconds=1, chat_id=chat_id)

    assert result["timed_out"] is True
    assert result["exit_code"] == -9
    assert cleanup == [4321]


def test_terminal_execute_output_cap_with_mock_process(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")
    monkeypatch.setattr("app.tools.terminal_execute._MAX_OUTPUT_BYTES", 32)

    class FakeProcess:
        pid = 9876
        returncode = 0

        def communicate(self, timeout=None):
            return "A" * 200, ""

    monkeypatch.setattr("app.tools.terminal_execute.subprocess.Popen", lambda *a, **k: FakeProcess())

    chat_id = "test-chat-mock-output"
    WorkspaceManager(tmp_path).create_or_bind(chat_id)

    result = terminal_execute(command="echo ignored", chat_id=chat_id)

    assert result["ok"] is True
    assert result["output_truncated"] is True
    assert "[TRUNCATED]" in result["output"]
