"""Task MCP tool contract tests."""

import asyncio

from app.tools.task import task


class FakeManager:
    async def wait_task(self, **kwargs):
        return {"ok": True, "action": "wait", **kwargs}

    async def tail_task(self, **kwargs):
        return {"ok": True, "action": "tail", **kwargs}

    async def kill_task(self, **kwargs):
        return {"ok": True, "action": "kill", **kwargs}

    async def list_tasks(self, **kwargs):
        return [{"ok": True, "action": "list", **kwargs}]

    async def status_task(self, **kwargs):
        return {"ok": True, "action": "status", **kwargs}

    async def send_input(self, **kwargs):
        return {"ok": True, "action": "send_input", **kwargs}


def test_task_docstring_has_anti_polling_rule():
    doc = task.__doc__ or ""
    assert "Do not call status in a loop. Use wait for completion." in doc
    assert all(len(sentence.split()) < 25 for sentence in doc.split("." ) if sentence.strip())


def test_task_actions_delegate(monkeypatch):
    from app.tools import task as module

    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "off")
    monkeypatch.setattr(module, "get_task_manager", lambda: FakeManager())

    async def run():
        result = await module.task("wait", "chat01", task_id="id")
        assert result["action"] == "wait"

        result = await module.task("tail", "chat01", task_id="id", lines=5)
        assert result["action"] == "tail"

        result = await module.task("send_input", "chat01", task_id="id", stdin_data="x")
        assert result["action"] == "send_input"

    asyncio.run(run())


def test_task_rejects_unknown_action(monkeypatch):
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "off")

    async def run():
        try:
            await task("unknown", "chat01")
        except ValueError as exc:
            assert "Unsupported task action" in str(exc)
        else:
            raise AssertionError("Expected ValueError")

    asyncio.run(run())


def test_task_enforce_mode_blocks_prebind(tmp_path, monkeypatch):
    from app.workspace_binding import register_workspace_binding
    from app.tools import task as module

    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")
    monkeypatch.setattr(module, "get_task_manager", lambda: FakeManager())

    async def run():
        # 1. Invalid chat_id -> E1
        res_e1 = await module.task("wait", "short")
        assert res_e1["ok"] is False
        assert res_e1["error"]["code"] == "E1"

        # 2. Unbound chat_id -> E6
        res_e6 = await module.task("wait", "unbound-chat-01")
        assert res_e6["ok"] is False
        assert res_e6["error"]["code"] == "E6"

        # 3. Bound chat_id -> Success
        chat_id = "bound-chat-task-01"
        ws_dir = tmp_path / chat_id
        ws_dir.mkdir(parents=True)
        (ws_dir / "meta.json").write_text('{"chat_id": "bound-chat-task-01", "created_at": "2026-10-07T12:00:00Z"}')
        register_workspace_binding(tmp_path, chat_id, "2026-10-07T12:00:00Z")

        res_bound = await module.task("wait", chat_id, task_id="tid-1")
        assert res_bound["ok"] is True
        assert res_bound["action"] == "wait"

    asyncio.run(run())
