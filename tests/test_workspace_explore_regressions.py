from pathlib import Path

from app.chat_workspace import WorkspaceManager
from app.tools.workspace_explore import workspace_explore


FIXTURE_ROOT = Path("bqa-trash") / "workspace_explore_regression_fixture"


def test_workspace_explore_read_window_clamps_and_reports_bounds(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")

    chat_id = "workspace-explore-regression"
    ws = WorkspaceManager(tmp_path).create_or_bind(chat_id).path
    fixture = ws / FIXTURE_ROOT
    fixture.mkdir(parents=True)
    target = fixture / "tiny.txt"
    target.write_text("a\nb\nc\n", encoding="utf-8")

    result = workspace_explore(
        path=str(target),
        action="read",
        start_line=99,
        line_count=2,
        chat_id=chat_id,
    )

    assert result["ok"] is True
    assert result["mode"] == "read"
    assert result["total_lines"] == 3
    assert result["lines"] == []


def test_workspace_explore_rejects_missing_path_in_enforce_mode():
    result = workspace_explore(
        path="bqa-trash/workspace-explore-missing-fixture.txt",
        action="read",
        chat_id="workspace-explore-regression",
    )

    assert result["ok"] is False
    assert "error" in result



def test_workspace_explore_bounds_total_recursive_entries(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")
    monkeypatch.setattr(
        "app.config.MAX_WORKSPACE_EXPLORE_ENTRIES",
        3,
        raising=False,
    )

    chat_id = "workspace-explore-entry-budget"
    workspace = WorkspaceManager(tmp_path).create_or_bind(chat_id).path
    root = workspace / "wide"
    root.mkdir()
    for index in range(4):
        directory = root / f"dir-{index}"
        directory.mkdir()
        (directory / f"file-{index}.txt").write_text("sample\n", encoding="utf-8")

    result = workspace_explore(
        path=str(root),
        action="tree",
        max_depth=5,
        chat_id=chat_id,
    )

    def count_entries(entries):
        return sum(
            1 + count_entries(entry.get("children", []))
            for entry in entries
        )

    assert result["ok"] is True
    assert count_entries(result["entries"]) == 3
    assert result["returned_entries"] == 3
    assert result["truncated"] is True
