from pathlib import Path

from app.chat_workspace import WorkspaceManager
from app.tools.workspace_edit import workspace_edit


def _bind_test_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")
    chat_id = f"workspace-edit-regression-{tmp_path.name}"
    ws = WorkspaceManager(tmp_path).create_or_bind(chat_id).path
    target = ws / "fixture.py"
    target.write_text(
        """\n"""
        "VALUE = 1\n"
        "\n"
        "def fixture_value():\n"
        "    return VALUE\n"
    )
    return chat_id, target


def test_workspace_edit_containment_rejects_outside_fixture(tmp_path, monkeypatch):
    chat_id, _ = _bind_test_workspace(tmp_path, monkeypatch)
    outside = "/etc/workspace_edit_regression.py"
    result = workspace_edit(
        path=outside,
        action="write",
        content="x = 1\n",
        chat_id=chat_id,
    )
    assert result["ok"] is False


def test_workspace_edit_anchor_mismatch_is_atomic(tmp_path, monkeypatch):
    chat_id, target = _bind_test_workspace(tmp_path, monkeypatch)
    before = target.read_text()
    result = workspace_edit(
        path=str(target),
        action="replace",
        old_text="missing-anchor",
        new_text="changed",
        expected_count=1,
        chat_id=chat_id,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "ANCHOR_COUNT_MISMATCH"
    assert target.read_text() == before


def test_workspace_edit_invalid_syntax_preserves_original_file(tmp_path, monkeypatch):
    chat_id, target = _bind_test_workspace(tmp_path, monkeypatch)
    before = target.read_text()
    result = workspace_edit(
        path=str(target),
        action="write",
        content="def broken(\n",
        chat_id=chat_id,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "SYNTAX_ERROR"
    assert target.read_text() == before


def test_workspace_edit_valid_write_then_append_is_atomic_flow(tmp_path, monkeypatch):
    chat_id, target = _bind_test_workspace(tmp_path, monkeypatch)
    result = workspace_edit(
        path=str(target),
        action="append",
        content="\nVALUE = 42\n",
        chat_id=chat_id,
    )
    assert result["ok"] is True
    assert "VALUE = 42" in target.read_text()
