from app.tools.workspace_explore import workspace_explore
from app.chat_workspace import WorkspaceManager


def test_workspace_explore_enforce_mode_requires_chat_id(monkeypatch):
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")
    res = workspace_explore(path=".", chat_id=None)
    assert res["ok"] is False
    assert res["error"]["code"] == "E6"


def test_workspace_explore_directory_and_read(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")

    chat_id = "test-chat-01"
    mgr = WorkspaceManager(tmp_path)
    bind_res = mgr.create_or_bind(chat_id)
    ws = bind_res.path
    (ws / "sample.txt").write_text("line 1\nline 2\nline 3\nline 4\nline 5\n", encoding="utf-8")
    (ws / "nested").mkdir()
    (ws / "nested" / "inner.txt").write_text("inner content\n", encoding="utf-8")
    (ws / "binary.bin").write_bytes(b"\x00\x01\x02\x03\x04\xff")

    # 1. Test directory explore
    list_res = workspace_explore(path=str(ws), action="list", chat_id=chat_id)
    assert list_res["ok"] is True
    assert list_res["mode"] == "directory"
    names = {e["name"] for e in list_res["entries"]}
    assert "sample.txt" in names
    assert "nested" in names

    # 2. Test windowed read
    read_res = workspace_explore(
        path=str(ws / "sample.txt"),
        action="read",
        start_line=2,
        line_count=2,
        chat_id=chat_id,
    )
    assert read_res["ok"] is True
    assert read_res["mode"] == "read"
    assert read_res["start_line"] == 2
    assert read_res["end_line"] == 3
    assert read_res["total_lines"] == 5
    assert read_res["has_more"] is True
    assert len(read_res["lines"]) == 2
    assert read_res["lines"][0]["text"] == "line 2"
    assert read_res["lines"][1]["text"] == "line 3"

    # 3. Test binary guard
    bin_res = workspace_explore(path=str(ws / "binary.bin"), action="read", chat_id=chat_id)
    assert bin_res["ok"] is True
    assert bin_res["mode"] == "binary"
    assert "size_bytes" in bin_res
