import json
import pytest
from app.chat_workspace import WorkspaceManager
from app.tools.terminal_execute import terminal_execute
from app.tools.workspace_explore import workspace_explore
from app.tools.workspace_edit import workspace_edit
from app.tools.workspace_search import workspace_search
from app.tools.web_intelligence import web_intelligence
from app.activity_log import read_mcp_command_activity


def test_mcp_super_tools_preserve_authentic_intent(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")
    monkeypatch.setattr("app.activity_log.MCP_COMMAND_ACTIVITY_LOG", tmp_path / "mcp_act.jsonl")

    chat_id = "test-intent-chat"
    mgr = WorkspaceManager(tmp_path)
    bind_res = mgr.create_or_bind(chat_id)
    ws = bind_res.path

    # 1. terminal_execute with intent
    term_intent = "Check kernel release and architecture"
    res1 = terminal_execute(
        command="uname -a",
        cwd=str(ws),
        chat_id=chat_id,
        intent=term_intent,
    )
    assert res1["ok"] is True

    # 2. workspace_explore with intent
    exp_intent = "Inspect workspace file tree structure"
    res2 = workspace_explore(
        path=str(ws),
        action="list",
        chat_id=chat_id,
        intent=exp_intent,
    )
    assert res2["ok"] is True

    # 3. workspace_edit with intent
    edit_intent = "Create initial project README file"
    res3 = workspace_edit(
        path=str(ws / "README.md"),
        action="write",
        content="# Test Project\n",
        chat_id=chat_id,
        intent=edit_intent,
    )
    assert res3["ok"] is True

    # 4. workspace_search with intent
    search_intent = "Search for project headline in documentation"
    res4 = workspace_search(
        query="Test Project",
        path=str(ws),
        chat_id=chat_id,
        intent=search_intent,
    )
    assert res4["ok"] is True

    # 5. task with intent
    from app.tools.task import task
    import asyncio
    task_intent = "Check active background processes"
    asyncio.run(task(
        action="list",
        chat_id=chat_id,
        intent=task_intent,
    ))

    # 6. Read workspace journal and verify intent persistence
    journal_path = ws / "journal.jsonl"
    assert journal_path.exists()
    journal_lines = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]

    # Collect op_started entries
    started_by_tool = {
        (entry.get("kind") or entry.get("tool")): entry["payload"]
        for entry in journal_lines
        if entry.get("type") == "op_started"
    }

    assert started_by_tool["terminal_execute"].get("intent") == term_intent
    assert started_by_tool["workspace_explore"].get("intent") == exp_intent
    assert started_by_tool["workspace_edit"].get("intent") == edit_intent
    assert started_by_tool["workspace_search"].get("intent") == search_intent
    assert started_by_tool["task"].get("intent") == task_intent

    # Verify activity log captured intent
    activities = read_mcp_command_activity(limit=10)
    assert len(activities) >= 1
    term_act = next(a for a in activities if a.get("command") == "uname -a")
    assert term_act.get("intent") == term_intent


def test_mcp_tools_omit_intent_when_unspecified(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")

    chat_id = "test-no-intent-chat"
    mgr = WorkspaceManager(tmp_path)
    bind_res = mgr.create_or_bind(chat_id)
    ws = bind_res.path

    res = terminal_execute(
        command="echo hello",
        cwd=str(ws),
        chat_id=chat_id,
    )
    assert res["ok"] is True

    journal_lines = [json.loads(line) for line in (ws / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
    started_payloads = [e["payload"] for e in journal_lines if e.get("type") == "op_started"]
    assert len(started_payloads) == 1
    assert "intent" not in started_payloads[0]
