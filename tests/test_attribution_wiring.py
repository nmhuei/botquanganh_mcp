"""Wave 2D wiring tests: chat-id attribution across the host-tool layer."""

import hashlib

import pytest

import app.config
from app.tools.health import HOST_TOOLS
from app.tools.host import (
    host_list_directory,
    host_read_file,
    host_run_command,
    host_search_text,
    host_write_file,
)
from app.tools.host_knowledge import host_knowledge

VALID_CHAT_ID = "wave2d-chat"


@pytest.fixture
def host_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(app.config, "HOST_RESTRICT_TO_WORKSPACE", True)
    monkeypatch.setattr(app.config, "HOST_COMMAND_POLICY", "guarded")
    monkeypatch.setattr(app.config, "MAX_OUTPUT_BYTES", 10_000)
    monkeypatch.setattr(app.config, "MAX_SINGLE_FILE_BYTES", 100_000)
    return tmp_path


@pytest.fixture
def audit_events(monkeypatch):
    events = []
    monkeypatch.setattr(
        "app.tools.host.log_audit_event",
        lambda event_type, details=None: events.append((event_type, dict(details or {}))),
    )
    return events


def set_mode(monkeypatch, mode):
    monkeypatch.setattr(app.config, "ATTRIBUTION_MODE", mode)


def test_off_mode_is_fully_inert(host_workspace, monkeypatch, audit_events):
    set_mode(monkeypatch, "off")

    plain = host_write_file("plain.txt", "hello")
    attributed = host_write_file("attributed.txt", "hello", chat_id=VALID_CHAT_ID)

    assert plain["ok"] is True
    assert attributed["ok"] is True
    assert set(attributed) == set(plain)
    assert "chat_id" not in attributed
    assert audit_events == []


@pytest.mark.parametrize("tool_call", ["read", "search"])
def test_off_mode_reads_with_chat_id_emit_nothing(
    host_workspace, monkeypatch, audit_events, tool_call
):
    set_mode(monkeypatch, "off")
    (host_workspace / "note.txt").write_text("data\n")

    if tool_call == "read":
        result = host_read_file("note.txt", chat_id=VALID_CHAT_ID)
    else:
        result = host_search_text("data", chat_id=VALID_CHAT_ID)

    assert result["ok"] is True
    assert "chat_id" not in result
    assert audit_events == []


def test_tag_mode_stamps_valid_chat_id_into_audit_event(
    host_workspace, monkeypatch, audit_events
):
    set_mode(monkeypatch, "tag")

    result = host_write_file("note.txt", "hello", chat_id=VALID_CHAT_ID)

    assert result["ok"] is True
    assert "chat_id" not in result
    assert len(audit_events) == 1
    event_type, details = audit_events[0]
    assert event_type == "HOST_TOOL_CALL"
    assert details["tool"] == "host_write_file"
    assert details["chat_id"] == VALID_CHAT_ID


def test_tag_mode_without_chat_id_records_nothing(
    host_workspace, monkeypatch, audit_events
):
    set_mode(monkeypatch, "tag")

    result = host_write_file("note.txt", "hello")

    assert result["ok"] is True
    assert audit_events == []


@pytest.mark.parametrize("mode", ["off", "tag", "strict"])
def test_invalid_chat_id_returns_e1_envelope(host_workspace, monkeypatch, mode):
    set_mode(monkeypatch, mode)

    result = host_read_file("whatever.txt", chat_id="short!")

    assert result["ok"] is False
    error = result["error"]
    assert error["code"] == "E1"
    assert error["name"] == "INVALID_CHAT_ID"
    assert error["message"]
    assert error["suggestion"]


def test_invalid_chat_id_blocks_the_write_entirely(host_workspace, monkeypatch):
    set_mode(monkeypatch, "off")

    result = host_write_file("evil.txt", "content", chat_id="nope")

    assert result["ok"] is False
    assert result["error"]["code"] == "E1"
    assert not (host_workspace / "evil.txt").exists()


def test_strict_mode_rejects_state_change_without_chat_id(
    host_workspace, monkeypatch, audit_events
):
    set_mode(monkeypatch, "strict")

    result = host_write_file("guarded.txt", "content")

    assert result["ok"] is False
    assert "strict" in result["error"]["message"]
    assert "chat_id" in result["error"]["message"]
    assert not (host_workspace / "guarded.txt").exists()
    assert audit_events == []


def test_strict_mode_allows_reads_without_chat_id(host_workspace, monkeypatch):
    set_mode(monkeypatch, "strict")
    (host_workspace / "present.txt").write_text("data\n")

    listed = host_list_directory(".")
    searched = host_search_text("data")

    assert listed["ok"] is True
    assert [item["name"] for item in listed["items"]] == ["present.txt"]
    assert searched["ok"] is True


def test_strict_mode_accepts_state_change_with_valid_chat_id(
    host_workspace, monkeypatch, audit_events
):
    set_mode(monkeypatch, "strict")

    result = host_write_file("ok.txt", "content", chat_id=VALID_CHAT_ID)

    assert result["ok"] is True
    assert (host_workspace / "ok.txt").read_text() == "content"
    assert audit_events[0][1]["chat_id"] == VALID_CHAT_ID


def test_intent_is_recorded_alongside_the_command_and_capped_at_200(
    host_workspace, monkeypatch, audit_events
):
    set_mode(monkeypatch, "off")
    calls = []
    monkeypatch.setattr(
        "app.tools.host.execute_host_command",
        lambda *args, **kwargs: calls.append(kwargs) or {"ok": True},
    )

    result = host_run_command("printf ok", intent="  fix   the\ndoor\t" + "y" * 300)

    assert result["ok"] is True
    assert calls == [
        {
            "cwd": None,
            "timeout_seconds": 30,
            "activity_source": "mcp",
            "activity_chat_id": None,
        }
    ]
    assert len(audit_events) == 1
    event_type, details = audit_events[0]
    assert event_type == "HOST_TOOL_CALL"
    assert details["tool"] == "host_run_command"
    assert details["command_sha256"] == hashlib.sha256(b"printf ok").hexdigest()
    assert details["intent"] == ("fix the door " + "y" * 187)[:200]
    assert len(details["intent"]) == 200
    assert "chat_id" not in details


def test_run_command_without_extras_emits_nothing(
    host_workspace, monkeypatch, audit_events
):
    set_mode(monkeypatch, "tag")
    monkeypatch.setattr(
        "app.tools.host.execute_host_command",
        lambda *args, **kwargs: {"ok": True},
    )

    result = host_run_command("printf ok")

    assert result["ok"] is True
    assert audit_events == []


def test_strict_mode_blocks_run_command_before_execution(
    host_workspace, monkeypatch, audit_events
):
    set_mode(monkeypatch, "strict")

    def explode(*args, **kwargs):
        raise AssertionError("executor must not run for unattributed commands")

    monkeypatch.setattr("app.tools.host.execute_host_command", explode)

    result = host_run_command("printf ok")

    assert result["ok"] is False
    assert "chat_id" in result["error"]["message"]
    assert audit_events == []


def test_knowledge_tool_rejects_invalid_chat_id(host_workspace, monkeypatch):
    set_mode(monkeypatch, "off")

    result = host_knowledge(chat_id="!!bad")

    assert result["ok"] is False
    assert result["error"]["code"] == "E1"


def test_knowledge_tool_stamps_in_tag_mode(host_workspace, monkeypatch, audit_events):
    set_mode(monkeypatch, "tag")

    result = host_knowledge(section="overview", chat_id=VALID_CHAT_ID)

    assert result["ok"] is True
    assert [event_type for event_type, _ in audit_events] == ["HOST_TOOL_CALL"]
    assert audit_events[0][1] == {"tool": "host_knowledge", "chat_id": VALID_CHAT_ID}


def test_host_tools_registry_lists_the_workspace_tools():
    assert "host_workspace_bind" in HOST_TOOLS
    assert "host_save_note" in HOST_TOOLS
