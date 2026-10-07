import pytest
from pathlib import Path
from app.tools.workspace_context import workspace_context


def test_workspace_context_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")

    chat_id = "test-chat-context-01"

    # 1. Bind
    bind_res = workspace_context(action="bind", chat_id=chat_id)
    assert bind_res["ok"] is True
    assert bind_res["chat_id"] == chat_id
    assert Path(bind_res["workspace_path"]).is_dir()

    # 2. List
    list_res = workspace_context(action="list")
    assert list_res["ok"] is True
    assert any(w["chat_id"] == chat_id for w in list_res["workspaces"])

    # 3. Note
    note_res = workspace_context(
        action="note",
        chat_id=chat_id,
        note="Initial discovery complete. Target port is 8080.",
    )
    assert note_res["ok"] is True
    assert note_res["saved"] is True

    # 4. Hypotheses (Negative Knowledge)
    hypo_res = workspace_context(
        action="hypotheses",
        chat_id=chat_id,
        hypothesis="Brute force admin pin with 6 digits",
        hypothesis_result="failed",
        do_not_retry=True,
        reason="Rate limit triggered after 3 attempts",
    )
    assert hypo_res["ok"] is True
    assert len(hypo_res["avoid_approaches"]) == 1
    assert "Rate limit" in hypo_res["avoid_approaches"][0]["reason"]

    # 5. State update
    state_res = workspace_context(
        action="state",
        chat_id=chat_id,
        state_update={"objective": "Solve CTF web challenge", "current_task": "Analyze SQL injection"},
    )
    assert state_res["ok"] is True
    assert state_res["current"]["objective"] == "Solve CTF web challenge"

    # 6. Resume briefing
    resume_res = workspace_context(action="resume", chat_id=chat_id)
    assert resume_res["ok"] is True
    assert "Solve CTF web challenge" in resume_res["resume_briefing_md"]
    assert "Rate limit" in resume_res["resume_briefing_md"]
    assert len(resume_res["avoid_approaches"]) == 1
