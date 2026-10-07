from app.chat_workspace import WorkspaceManager
from app.tools.terminal_execute import terminal_execute


def test_terminal_execute_adaptive_detach(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    chat_id = "test-adaptive"
    workspace = WorkspaceManager(tmp_path).create_or_bind(chat_id)

    result = terminal_execute(
        command="python3 -c 'import time; print(\"started\"); time.sleep(6)'",
        cwd=str(workspace.path),
        chat_id=chat_id,
        wait_ms_before_async=100,
    )

    assert result.get("ok") is True
    assert result.get("detached") is True
    assert result.get("task_id")


def test_terminal_execute_background_returns_task_id(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    chat_id = "test-background"
    workspace = WorkspaceManager(tmp_path).create_or_bind(chat_id)

    result = terminal_execute(
        command="python3 -c 'import time; time.sleep(1)'",
        cwd=str(workspace.path),
        chat_id=chat_id,
        background=True,
    )

    assert result.get("task_id")
    assert result.get("detached") is True
