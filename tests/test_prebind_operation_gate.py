"""Comprehensive tests for MCP Pre-Bind Operation Gate across all 8 Super-Tools."""

import asyncio
import json
from pathlib import Path

import pytest

import app.config
from app.workspace_binding import clear_workspace_bindings, has_workspace_binding
from app.tools.server_info import server_info
from app.tools.terminal_execute import terminal_execute
from app.tools.web_intelligence import web_intelligence
from app.tools.workspace_context import workspace_context
from app.tools.workspace_edit import workspace_edit
from app.tools.workspace_explore import workspace_explore
from app.tools.workspace_search import workspace_search
from app.tools.task import task


@pytest.fixture(autouse=True)
def setup_environment(tmp_path, monkeypatch):
    clear_workspace_bindings()
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")
    yield
    clear_workspace_bindings()


def test_bootstrap_operations_permitted_prebind():
    # 1. server_info
    res_server = server_info()
    assert res_server["ok"] is True

    # 2. workspace_context(bind)
    res_bind = workspace_context(action="bind", chat_id="prebind-session-01")
    assert res_bind["ok"] is True
    assert res_bind["chat_id"] == "prebind-session-01"

    # 3. workspace_context(list)
    res_list = workspace_context(action="list")
    assert res_list["ok"] is True
    assert isinstance(res_list["workspaces"], list)


def test_malformed_chat_id_returns_e1():
    # Even on server_info, a malformed chat_id must return E1
    res = server_info(chat_id="bad")
    assert res["ok"] is False
    assert res["error"]["code"] == "E1"

    res_ctx = workspace_context(action="bind", chat_id="bad")
    assert res_ctx["ok"] is False
    assert res_ctx["error"]["code"] == "E1"


def test_invalid_context_action_returns_invalid_action():
    res = workspace_context(action="destroy_everything")
    assert res["ok"] is False
    assert res["error"]["code"] == "INVALID_ACTION"


def test_prebind_blocked_operations_return_e6(tmp_path):
    unbound_id = "unbound-session-01"

    # Context actions blocked pre-bind
    res_note = workspace_context(action="note", chat_id=unbound_id, note="hello")
    assert res_note["ok"] is False
    assert res_note["error"]["code"] == "E6"

    res_state = workspace_context(action="state", chat_id=unbound_id)
    assert res_state["ok"] is False
    assert res_state["error"]["code"] == "E6"

    res_hypo = workspace_context(action="hypotheses", chat_id=unbound_id, hypothesis="test")
    assert res_hypo["ok"] is False
    assert res_hypo["error"]["code"] == "E6"

    res_resume = workspace_context(action="resume", chat_id=unbound_id)
    assert res_resume["ok"] is False
    assert res_resume["error"]["code"] == "E6"

    # Explore blocked pre-bind
    res_explore = workspace_explore(path=str(tmp_path), action="list", chat_id=unbound_id)
    assert res_explore["ok"] is False
    assert res_explore["error"]["code"] == "E6"

    # Search blocked pre-bind
    res_search = workspace_search(path=str(tmp_path), query="abc", chat_id=unbound_id)
    assert res_search["ok"] is False
    assert res_search["error"]["code"] == "E6"

    # Edit blocked pre-bind
    res_edit = workspace_edit(path=str(tmp_path / "f.txt"), action="write", content="x", chat_id=unbound_id)
    assert res_edit["ok"] is False
    assert res_edit["error"]["code"] == "E6"

    # Terminal blocked pre-bind
    res_term = terminal_execute(command="echo hi", cwd=str(tmp_path), chat_id=unbound_id)
    assert res_term["ok"] is False
    assert res_term["error"]["code"] == "E6"

    # Task blocked pre-bind
    res_task = asyncio.run(task(action="list", chat_id=unbound_id))
    assert res_task["ok"] is False
    assert res_task["error"]["code"] == "E6"

    # Web intelligence blocked pre-bind
    res_web = web_intelligence(url="http://127.0.0.1", chat_id=unbound_id)
    assert res_web["ok"] is False
    assert res_web["error"]["code"] == "E6"


def test_disk_existing_meta_does_not_grant_prebind_access(tmp_path):
    """Having meta.json on disk does NOT grant access without an in-memory session bind."""
    chat_id = "on-disk-session-01"
    ws_dir = tmp_path / chat_id
    ws_dir.mkdir(parents=True)
    (ws_dir / "meta.json").write_text(json.dumps({"chat_id": chat_id, "created_at": "2026-10-07T10:00:00Z"}))

    assert not has_workspace_binding(tmp_path, chat_id)

    # Calling an operational tool without bind must return E6
    res = workspace_context(action="state", chat_id=chat_id)
    assert res["ok"] is False
    assert res["error"]["code"] == "E6"

    res_explore = workspace_explore(path=str(tmp_path), action="list", chat_id=chat_id)
    assert res_explore["ok"] is False
    assert res_explore["error"]["code"] == "E6"


def test_bind_then_operational_tools_succeed(tmp_path):
    chat_id = "bound-session-flow-01"

    # 1. Bind
    res_bind = workspace_context(action="bind", chat_id=chat_id)
    assert res_bind["ok"] is True
    assert has_workspace_binding(tmp_path, chat_id)

    # 2. Context note
    res_note = workspace_context(action="note", chat_id=chat_id, note="Step 1 complete.")
    assert res_note["ok"] is True

    # 3. Explore
    res_explore = workspace_explore(path=str(tmp_path), action="list", chat_id=chat_id)
    assert res_explore["ok"] is True

    # 4. Search
    res_search = workspace_search(path=str(tmp_path), query="Step 1", chat_id=chat_id)
    assert res_search["ok"] is True

    # 5. Terminal execute
    res_term = terminal_execute(command="echo 'success'", cwd=str(tmp_path), chat_id=chat_id)
    assert res_term["ok"] is True


def test_simulated_server_restart_requires_rebind(tmp_path):
    chat_id = "restart-test-session-01"

    # 1. Bind and verify operational tool works
    workspace_context(action="bind", chat_id=chat_id)
    res_note1 = workspace_context(action="note", chat_id=chat_id, note="Before restart")
    assert res_note1["ok"] is True

    # 2. Simulate server restart: in-memory registry cleared
    clear_workspace_bindings()

    # 3. Operational tool now returns E6
    res_blocked = workspace_context(action="note", chat_id=chat_id, note="After restart")
    assert res_blocked["ok"] is False
    assert res_blocked["error"]["code"] == "E6"

    # 4. List is still permitted
    res_list = workspace_context(action="list")
    assert res_list["ok"] is True
    assert any(w["chat_id"] == chat_id for w in res_list["workspaces"])

    # 5. Re-bind to existing workspace
    res_rebind = workspace_context(action="bind", resume_id=chat_id)
    assert res_rebind["ok"] is True

    # 6. Operational tool works again
    res_note2 = workspace_context(action="note", chat_id=chat_id, note="After rebind")
    assert res_note2["ok"] is True
