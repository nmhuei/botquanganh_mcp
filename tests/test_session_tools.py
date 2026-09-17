"""Unit and integration tests for host_session_list and host_session_bind FastMCP tools."""

import asyncio
from pathlib import Path
import pytest

import app.config
from app.chat_identity import bind_chat, get_chat_id
from app.tools.host import _guard_chat_id, host_run_command
from app.tools.workspace_tools import host_session_bind, host_session_list, host_save_note


@pytest.fixture(autouse=True)
def configure_test_workspaces(tmp_path: Path, monkeypatch):
    from app.chat_identity import _CHAT_ID
    token = _CHAT_ID.set(None)
    monkeypatch.setattr(app.config, "HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr(app.config, "HOST_CHAT_ROOT", tmp_path)
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(app.config, "HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr(app.config, "ATTRIBUTION_MODE", "enforce")
    yield
    _CHAT_ID.reset(token)


def test_host_session_bind_new_session(tmp_path: Path):
    res = asyncio.run(host_session_bind(new=True, label="unit-test-proj"))
    assert res["ok"] is True
    assert res["is_new"] is True
    assert "unit-test-proj" in res["session_id"]
    assert Path(res["workspace_dir"]).is_dir()
    assert (Path(res["workspace_dir"]) / "meta.json").is_file()
    assert (tmp_path / ".last_session").is_file()


def test_host_session_bind_and_context_rehydration(tmp_path: Path):
    # 1. Create a session and write some notes and commands
    res_create = asyncio.run(host_session_bind(new=True, label="project-alpha"))
    session_id = res_create["session_id"]
    ws_dir = Path(res_create["workspace_dir"])

    # Save a note
    res_note = asyncio.run(host_save_note("Initial note for project alpha", chat_id=session_id))
    assert res_note["ok"] is True

    # Run a command inside this session
    res_cmd = host_run_command("echo 'hello alpha'", chat_id=session_id)
    assert res_cmd["ok"] is True

    # 2. Now call host_session_list -> should discover project-alpha
    res_list = asyncio.run(host_session_list())
    assert res_list["ok"] is True
    assert res_list["total_count"] >= 1
    found = next((s for s in res_list["sessions"] if s["session_id"] == session_id), None)
    assert found is not None
    assert found["is_latest"] is True

    # 3. Call host_session_bind to re-connect to this session
    res_bind = asyncio.run(host_session_bind(session_id=session_id))
    assert res_bind["ok"] is True
    assert res_bind["is_new"] is False
    assert res_bind["session_id"] == session_id
    assert "Initial note for project alpha" in res_bind["recent_notes"]


def test_host_session_bind_defaults_to_latest(tmp_path: Path):
    # Create two sessions
    res1 = asyncio.run(host_session_bind(new=True, label="first"))
    res2 = asyncio.run(host_session_bind(new=True, label="second"))

    # When session_id is omitted or "latest", should bind to the latest (res2)
    res_latest = asyncio.run(host_session_bind())
    assert res_latest["ok"] is True
    assert res_latest["session_id"] == res2["session_id"]


def test_gating_blocks_commands_before_session_established(tmp_path: Path, monkeypatch):
    from app.chat_identity import _CHAT_ID
    _CHAT_ID.set(None)
    monkeypatch.setattr("app.chat_identity.get_chat_id", lambda: None)
    monkeypatch.setattr("app.chat_identity.get_active_workspace", lambda: None)

    # Calling host_run_command without chat_id or bound session must fail
    res = host_run_command("echo 'blocked'")
    assert res["ok"] is False
    error = res.get("error", {})
    assert "instructions" in error or "suggestion" in error
    assert "host_workspace_bind" in str(error) or "host_workspace_list" in str(error)
