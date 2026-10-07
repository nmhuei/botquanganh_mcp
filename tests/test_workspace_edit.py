import pytest
from pathlib import Path
from app.tools.workspace_edit import workspace_edit
from app.chat_workspace import WorkspaceManager


def test_workspace_edit_enforce_mode_requires_chat_id(monkeypatch):
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")
    res = workspace_edit(path="foo.py", action="write", content="print('hello')", chat_id=None)
    assert res["ok"] is False
    assert res["error"]["code"] == "E6"


def test_workspace_edit_omitted_action_is_rejected_without_mutation(tmp_path):
    target = tmp_path / "existing.py"
    original = b"print('keep')\n"
    target.write_bytes(original)

    with pytest.raises(TypeError):
        workspace_edit(path=str(target), content="print('changed')\n")

    assert target.read_bytes() == original


def test_workspace_edit_omitted_write_content_preserves_original_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")

    mgr = WorkspaceManager(tmp_path)
    ws = mgr.create_or_bind("test-chat-edit").path
    target = ws / "existing.py"
    original = b"print('keep')\n"
    target.write_bytes(original)

    res = workspace_edit(
        path=str(target),
        action="write",
        chat_id="test-chat-edit",
    )

    assert res["ok"] is False
    assert res["error"]["code"] == "MISSING_CONTENT"
    assert target.read_bytes() == original


def test_workspace_edit_write_append_replace(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")

    chat_id = "test-chat-edit"
    mgr = WorkspaceManager(tmp_path)
    bind_res = mgr.create_or_bind(chat_id)
    ws = bind_res.path

    target_file = str(ws / "main.py")

    # 1. Test write with valid python
    write_res = workspace_edit(
        path=target_file,
        action="write",
        content="def greet():\n    return 'hello'\n",
        chat_id=chat_id,
    )
    assert write_res["ok"] is True
    assert write_res["bytes_written"] > 0

    # 2. Test syntax error prevention
    bad_py_res = workspace_edit(
        path=target_file,
        action="write",
        content="def broken_syntax(\n",
        chat_id=chat_id,
    )
    assert bad_py_res["ok"] is False
    assert bad_py_res["error"]["code"] == "SYNTAX_ERROR"
    # File content must still be intact!
    assert "def greet" in (ws / "main.py").read_text()

    # 3. Test anchored replace
    replace_res = workspace_edit(
        path=target_file,
        action="replace",
        old_text="'hello'",
        new_text="'world'",
        expected_count=1,
        chat_id=chat_id,
    )
    assert replace_res["ok"] is True
    assert "return 'world'" in (ws / "main.py").read_text()

    # 4. Test anchor count mismatch fails safely
    mismatch_res = workspace_edit(
        path=target_file,
        action="replace",
        old_text="non_existent_text",
        new_text="something",
        expected_count=1,
        chat_id=chat_id,
    )
    assert mismatch_res["ok"] is False
    assert mismatch_res["error"]["code"] == "ANCHOR_COUNT_MISMATCH"

    # 5. Test append
    append_res = workspace_edit(
        path=target_file,
        action="append",
        content="\nVALUE = 42\n",
        chat_id=chat_id,
    )
    assert append_res["ok"] is True
    assert "VALUE = 42" in (ws / "main.py").read_text()
