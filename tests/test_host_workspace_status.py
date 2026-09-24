"""Unit and integration tests for host_workspace_status tool."""

from pathlib import Path
import pytest

import app.config
from app.tools.workspace_tools import host_workspace_bind, host_workspace_status


@pytest.mark.anyio
async def test_host_workspace_status_existing(tmp_path, monkeypatch):
    chat_root = tmp_path / "chat_workspaces"
    chat_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app.config, "HOST_CHAT_ROOT", str(chat_root))
    monkeypatch.setattr(app.config, "HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr(app.config, "HOST_CHAT_QUOTA_MB", 1024)

    # Bind a new workspace
    bind_res = await host_workspace_bind(label="ctf-test")
    assert bind_res["ok"] is True
    chat_id = bind_res["chat_id"]

    # Check status
    status_res = host_workspace_status(chat_id=chat_id)
    assert status_res["ok"] is True
    assert status_res["chat_id"] == chat_id
    assert status_res["quota"]["limit_mb"] == 1024
    assert status_res["usage"]["file_count"] >= 0
    assert status_res["state"]["has_state_file"] is True


def test_host_workspace_status_unbound(tmp_path, monkeypatch):
    chat_root = tmp_path / "chat_workspaces"
    chat_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app.config, "HOST_CHAT_ROOT", str(chat_root))
    monkeypatch.setattr(app.config, "HOST_CHAT_WORKSPACES", True)

    status_res = host_workspace_status(chat_id="nonexistent-chat-123")
    assert status_res["ok"] is False
    # In enforce mode, uncreated workspace fails with E6 or WORKSPACE_NOT_FOUND
    err_code = status_res["error"]["code"]
    assert err_code in {"E6", "WORKSPACE_NOT_FOUND"}
