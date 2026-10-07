from pathlib import Path

from app.tools.workspace_context import workspace_context


def _isolate_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path / "bqa-trash"))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path / "bqa-trash")
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path / "bqa-trash")
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")


def test_workspace_context_bind_creates_persistent_baseline(monkeypatch, tmp_path):
    _isolate_workspace(monkeypatch, tmp_path)

    result = workspace_context(action="bind", chat_id="regression-baseline-01")

    assert result["ok"] is True
    workspace = Path(result["workspace_path"])
    assert (workspace / "CURRENT.json").is_file()
    assert (workspace / "STATE.md").is_file()
    assert (workspace / "hypotheses.json").is_file()


def test_workspace_context_hypothesis_resume_only_surfaces_do_not_retry(monkeypatch, tmp_path):
    _isolate_workspace(monkeypatch, tmp_path)
    chat_id = "regression-hypothesis-01"
    workspace_context(action="bind", chat_id=chat_id)

    workspace_context(
        action="hypotheses",
        chat_id=chat_id,
        hypothesis="Approach A",
        hypothesis_result="failed",
        do_not_retry=False,
        reason="Not permanently ruled out",
    )
    workspace_context(
        action="hypotheses",
        chat_id=chat_id,
        hypothesis="Approach B",
        hypothesis_result="failed",
        do_not_retry=True,
        reason="Confirmed invalid path",
    )

    result = workspace_context(action="resume", chat_id=chat_id)

    assert result["ok"] is True
    assert len(result["avoid_approaches"]) == 1
    assert result["avoid_approaches"][0]["hypothesis"] == "Approach B"
    assert "Confirmed invalid path" in result["resume_briefing_md"]
