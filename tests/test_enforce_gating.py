"""B2 gating tests: under ATTRIBUTION_MODE=enforce nothing runs unbound.

Matrix over {missing, invalid, valid} chat_id x {read tool, write tool,
command run}, plus the host_workspace_bind exemption, host_save_note parity,
legacy-mode regressions (off/tag/strict), and the defensive paths that keep
the gate inert when the concurrent chat_identity/chat_errors pieces are
absent or partially landed.
"""

import asyncio
import inspect
import sys
import types

import pytest

import app.config
from app.tools.ctf_http import ctf_fetch_url, ctf_render_fetch_result
from app.tools.health import HOST_TOOLS
from app.tools.host import (
    BIND_EXEMPT_TOOLS,
    host_append_file,
    host_check_command,
    host_list_directory,
    host_make_directory,
    host_read_file,
    host_replace_in_file,
    host_run_command,
    host_search_text,
    host_write_file,
)
from app.tools.host_knowledge import host_knowledge
from app.tools.workspace_tools import host_save_note, host_workspace_bind

VALID_ID = "enforce-chat"
OTHER_VALID_ID = "second-chat"
INVALID_ID = "../escape"

# Known B2 gap: the CTF surface has no chat_id parameter yet and lives in a
# file outside this change's scope; it stays structurally ungated until then.
CTF_UNGATED_TOOLS = frozenset({"ctf_fetch_url", "ctf_render_fetch_result"})

TOOL_FUNCTIONS = {
    "host_list_directory": host_list_directory,
    "host_read_file": host_read_file,
    "host_write_file": host_write_file,
    "host_replace_in_file": host_replace_in_file,
    "host_append_file": host_append_file,
    "host_make_directory": host_make_directory,
    "host_search_text": host_search_text,
    "host_check_command": host_check_command,
    "host_run_command": host_run_command,
    "ctf_fetch_url": ctf_fetch_url,
    "ctf_render_fetch_result": ctf_render_fetch_result,
    "host_knowledge": host_knowledge,
    "host_workspace_bind": host_workspace_bind,
    "host_save_note": host_save_note,
}


@pytest.fixture
def host_workspace(tmp_path, monkeypatch):
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir(parents=True, exist_ok=True)
    chat_root = tmp_path / "chats_storage"
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", ws_dir)
    monkeypatch.setattr(app.config, "HOST_RESTRICT_TO_WORKSPACE", True)
    monkeypatch.setattr(app.config, "HOST_COMMAND_POLICY", "guarded")
    monkeypatch.setattr(app.config, "MAX_OUTPUT_BYTES", 10_000)
    monkeypatch.setattr(app.config, "MAX_SINGLE_FILE_BYTES", 100_000)
    monkeypatch.setattr(app.config, "HOST_CHAT_ROOT", str(chat_root))
    monkeypatch.setattr(app.config, "HOST_CHAT_WORKSPACES", True)
    for cid in (VALID_ID, OTHER_VALID_ID):
        target = chat_root / cid
        target.mkdir(parents=True, exist_ok=True)
        (target / "meta.json").write_text(
            f'{{"chat_id": "{cid}", "created_at": "2026-08-26T00:00:00+00:00", "schema": 1, "next_seq": 1}}\n',
            encoding="utf-8",
        )
    return ws_dir


@pytest.fixture
def enforce_mode(monkeypatch):
    # Works before AND after the concurrent config/chat_identity changes land:
    # post-merge is_enforcing() reads this same attribute; pre-merge the raw
    # fallback read in app.tools.host picks it up.
    monkeypatch.setattr(app.config, "ATTRIBUTION_MODE", "enforce")


@pytest.fixture
def audit_events(monkeypatch):
    events = []
    monkeypatch.setattr(
        "app.tools.host.log_audit_event",
        lambda event_type, details=None: events.append(
            (event_type, dict(details or {}))
        ),
    )
    return events


@pytest.fixture
def executor_calls(monkeypatch):
    calls = []

    def recorder(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True, "stdout": "", "stderr": "", "exit_code": 0}

    monkeypatch.setattr("app.tools.host.execute_host_command", recorder)
    return calls


@pytest.fixture
def blocked_fs_calls(monkeypatch):
    """Recorders for every filesystem function the fs tools can dispatch to."""
    recorded = {}
    benign = {
        "read_text_file": {"ok": True, "content": ""},
        "write_text_file": {"ok": True},
        "append_text_file": {"ok": True},
        "replace_text_in_file": {"ok": True},
        "make_directory": {"ok": True},
        "list_directory": {"ok": True, "items": []},
        "search_text": {"ok": True, "results": []},
    }
    for name, reply in benign.items():
        calls = []

        def make_recorder(calls_, reply_):
            def recorder(*args, **kwargs):
                calls_.append((args, kwargs))
                return reply_

            return recorder

        monkeypatch.setattr(f"app.tools.host.{name}", make_recorder(calls, reply))
        recorded[name] = calls
    return recorded


@pytest.fixture
def blocked_policy_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.tools.host.inspect_host_command",
        lambda command: calls.append(command) or {},
    )
    return calls


@pytest.fixture
def blocked_knowledge_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.host.inventory.list_guide_files",
        lambda *args, **kwargs: calls.append("guides") or [],
    )
    monkeypatch.setattr(
        "app.host.inventory.get_tool_inventory",
        lambda *args, **kwargs: calls.append("inventory")
        or {"summary": {}, "tools": []},
    )
    return calls


READ_CALLS = [
    lambda: host_list_directory("."),
    lambda: host_read_file("note.txt"),
    lambda: host_search_text("data"),
    lambda: host_check_command("printf ok"),
    lambda: host_knowledge(section="overview"),
]


# ------------------------------------------------------- enforce: missing id


@pytest.mark.parametrize(
    "invoke",
    READ_CALLS,
    ids=["list", "read", "search", "check", "knowledge"],
)
def test_enforce_rejects_unbound_reads_with_e6(
    host_workspace, enforce_mode, audit_events, invoke
):
    result = invoke()

    assert result["ok"] is False
    assert result["error"]["code"] == "E6"
    assert audit_events == []


@pytest.mark.parametrize(
    "invoke",
    [
        lambda: host_write_file("out.txt", "content"),
        lambda: host_replace_in_file("out.txt", "a", "b"),
        lambda: host_append_file("out.txt", "content"),
        lambda: host_make_directory("subdir"),
    ],
    ids=["write", "replace", "append", "mkdir"],
)
def test_enforce_rejects_unbound_writes_with_e6_before_any_fs_call(
    host_workspace, enforce_mode, audit_events, blocked_fs_calls, invoke
):
    result = invoke()

    assert result["ok"] is False
    assert result["error"]["code"] == "E6"
    assert all(calls == [] for calls in blocked_fs_calls.values())
    assert audit_events == []
    assert not (host_workspace / "out.txt").exists()
    assert not (host_workspace / "subdir").exists()


def test_enforce_blocks_run_command_before_the_executor_runs(
    host_workspace, enforce_mode, audit_events, executor_calls
):
    result = host_run_command("printf ok")

    assert result["ok"] is False
    assert result["error"]["code"] == "E6"
    assert executor_calls == []
    assert audit_events == []


def test_enforce_rejection_tells_the_caller_to_bind_first(
    host_workspace, enforce_mode
):
    result = host_read_file("note.txt")

    error_text = (
        result["error"]["message"] + " " + result["error"]["suggestion"]
    )
    assert result["error"]["code"] == "E6"
    assert "host_workspace_bind" in error_text


# ------------------------------------------------------- enforce: invalid id


@pytest.mark.parametrize(
    "invoke",
    [
        lambda: host_read_file("note.txt", chat_id=INVALID_ID),
        lambda: host_write_file("out.txt", "content", chat_id=INVALID_ID),
        lambda: host_run_command("printf ok", chat_id=INVALID_ID),
        lambda: host_knowledge(section="overview", chat_id=INVALID_ID),
    ],
    ids=["read", "write", "run", "knowledge"],
)
def test_enforce_rejects_malformed_ids_with_e1_before_execution(
    host_workspace,
    enforce_mode,
    audit_events,
    executor_calls,
    blocked_fs_calls,
    blocked_knowledge_calls,
    invoke,
):
    result = invoke()

    assert result["ok"] is False
    assert result["error"]["code"] == "E1"
    assert executor_calls == []
    assert all(calls == [] for calls in blocked_fs_calls.values())
    assert blocked_knowledge_calls == []
    assert audit_events == []


# --------------------------------------------------------- enforce: valid id


def test_enforce_allows_reads_with_valid_id_and_keeps_stamping(
    host_workspace, enforce_mode, audit_events
):
    (host_workspace / "note.txt").write_text("data\n")

    listed = host_list_directory(".", chat_id=VALID_ID)
    read = host_read_file("note.txt", chat_id=VALID_ID)

    assert listed["ok"] is True
    assert [item["name"] for item in listed["items"]] == ["note.txt"]
    assert read["ok"] is True
    stamped = [details for _, details in audit_events]
    assert all(details.get("chat_id") == VALID_ID for details in stamped)


def test_enforce_allows_writes_with_valid_id_and_stamps_audit(
    host_workspace, enforce_mode, audit_events
):
    result = host_write_file("ok.txt", "content", chat_id=VALID_ID)

    assert result["ok"] is True
    assert (host_workspace / "ok.txt").read_text() == "content"
    assert len(audit_events) == 1
    event_type, details = audit_events[0]
    assert event_type == "HOST_TOOL_CALL"
    assert details["tool"] == "host_write_file"
    assert details["chat_id"] == VALID_ID


def test_enforce_allows_run_command_with_valid_id_and_stamps_audit(
    host_workspace, enforce_mode, audit_events, executor_calls
):
    result = host_run_command("printf ok", intent="verify", chat_id=VALID_ID)

    assert result["ok"] is True
    assert len(executor_calls) == 1
    assert len(audit_events) == 1
    event_type, details = audit_events[0]
    assert event_type == "HOST_TOOL_CALL"
    assert details["tool"] == "host_run_command"
    assert details["chat_id"] == VALID_ID
    assert details["intent"] == "verify"


def test_enforce_knowledge_with_valid_id_stamps_audit(
    host_workspace, enforce_mode, audit_events
):
    result = host_knowledge(section="overview", chat_id=VALID_ID)

    assert result["ok"] is True
    assert audit_events == [("HOST_TOOL_CALL", {"tool": "host_knowledge", "chat_id": VALID_ID})]


# ------------------------------------------------------------ context-bound


def test_context_bound_chat_id_satisfies_enforce_without_a_param(
    host_workspace, enforce_mode, audit_events
):
    pytest.importorskip("app.chat_identity")
    from app.chat_identity import bound_chat

    (host_workspace / "ctx.txt").write_text("data\n")

    with bound_chat(VALID_ID):
        result = host_read_file("ctx.txt")

    assert result["ok"] is True
    assert audit_events[0][1]["chat_id"] == VALID_ID


# ---------------------------------------------------------------- exemption


@pytest.fixture
def chat_root(tmp_path, monkeypatch):
    monkeypatch.setattr(app.config, "HOST_CHAT_ROOT", str(tmp_path), raising=False)
    monkeypatch.setattr(app.config, "HOST_CHAT_WORKSPACES", True, raising=False)
    # Create valid meta for VALID_ID
    ws_dir = tmp_path / VALID_ID
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "meta.json").write_text(
        f'{{"chat_id": "{VALID_ID}", "created_at": "2026-08-26T00:00:00+00:00", "schema": 1, "next_seq": 1}}\n',
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def fake_workspace_infra(monkeypatch, tmp_path):
    class FakeWorkspaceManager:
        def __init__(self, root):
            self.root = root

        def create_or_bind(self, chat_id=None, **kwargs):
            target = chat_id or kwargs.get("label") or VALID_ID
            path = tmp_path / "chats" / target
            return types.SimpleNamespace(path=path, created=True, resumed_hint=None, chat_id=target)

    module = types.ModuleType("app.chat_workspace")
    module.WorkspaceManager = FakeWorkspaceManager
    monkeypatch.setitem(sys.modules, "app.chat_workspace", module)


def test_only_host_workspace_bind_is_exempt():
    assert BIND_EXEMPT_TOOLS == frozenset({"host_workspace_bind"})


def test_bind_works_under_enforce_without_any_prior_binding(
    chat_root, enforce_mode, fake_workspace_infra
):
    result = asyncio.run(host_workspace_bind(chat_id=VALID_ID))

    assert result["ok"] is True
    assert result["chat_id"] == VALID_ID
    assert result["workspace"].endswith(str(chat_root / "chats" / VALID_ID))


def test_bind_still_validates_ids_under_enforce(chat_root, enforce_mode):
    result = asyncio.run(host_workspace_bind(chat_id=INVALID_ID))

    assert result["ok"] is False
    assert result["error"]["code"] == "E1"


# ------------------------------------------------------------ save-note gate


def test_enforce_requires_an_existing_binding_for_notes(
    chat_root, enforce_mode
):
    result = asyncio.run(host_save_note("unbound"))

    assert result["ok"] is False
    assert result["error"]["code"] == "E6"
    assert not (chat_root / "notes").exists()


def test_enforce_note_with_valid_id_lands_in_its_own_log(
    chat_root, enforce_mode
):
    result = asyncio.run(host_save_note("bound note", chat_id=VALID_ID))

    log_file = chat_root / VALID_ID / "notes" / "log.txt"
    assert result["ok"] is True
    assert result["path"] == str(log_file)
    assert log_file.read_text().endswith(" bound note\n")


def test_enforce_note_with_invalid_id_is_still_e1(chat_root, enforce_mode):
    result = asyncio.run(host_save_note("hi", chat_id=INVALID_ID))

    assert result["ok"] is False
    assert result["error"]["code"] == "E1"


# ----------------------------------------------------- legacy-mode stability


@pytest.mark.parametrize("mode", ["off", "tag"])
def test_off_and_tag_modes_still_execute_without_any_id(
    host_workspace, monkeypatch, audit_events, executor_calls, mode
):
    monkeypatch.setattr(app.config, "ATTRIBUTION_MODE", mode)
    (host_workspace / "note.txt").write_text("data\n")

    read = host_read_file("note.txt")
    written = host_write_file("out.txt", "content")
    ran = host_run_command("printf ok")

    assert read["ok"] is True
    assert written["ok"] is True
    assert ran["ok"] is True
    assert "E6" not in str(read) and "E6" not in str(written)


def test_strict_mode_keeps_its_writes_only_rejection_not_e6(
    host_workspace, monkeypatch, audit_events
):
    monkeypatch.setattr(app.config, "ATTRIBUTION_MODE", "strict")
    (host_workspace / "note.txt").write_text("data\n")

    read = host_read_file("note.txt")
    write = host_write_file("guarded.txt", "content")

    assert read["ok"] is True
    assert write["ok"] is False
    assert write["error"]["code"] != "E6"
    assert "strict" in write["error"]["message"]
    assert not (host_workspace / "guarded.txt").exists()
    assert audit_events == []


@pytest.mark.parametrize("mode", ["banana", "", "ON-TAG"])
def test_unknown_mode_values_never_activate_the_gate(
    host_workspace, monkeypatch, mode
):
    monkeypatch.setattr(app.config, "ATTRIBUTION_MODE", mode)

    result = host_read_file("missing-but-fine.txt")

    # Behaves exactly as today: the tool runs (and reports its own filesystem
    # miss) instead of being rejected by the binding gate.
    assert result["error"]["code"] != "E6"


def test_absent_config_value_never_activates_the_gate(
    host_workspace, monkeypatch
):
    monkeypatch.delattr(app.config, "ATTRIBUTION_MODE", raising=False)

    result = host_read_file("whatever.txt")

    assert result["error"]["code"] != "E6"


# ------------------------------------------------------------ defensive paths


def test_e6_falls_back_to_hand_built_envelope_without_chat_errors(
    host_workspace, enforce_mode, monkeypatch
):
    monkeypatch.setitem(sys.modules, "app.chat_errors", None)

    result = host_read_file("note.txt")

    assert result["ok"] is False
    error = result["error"]
    assert error["code"] == "E6"
    assert error["name"] == "BIND_REQUIRED"
    assert "host_workspace_bind" in error["message"] + error["suggestion"]
    assert set(error) >= {"code", "name", "message", "suggestion"}


def test_valid_flow_survives_missing_chat_errors_module(
    chat_root, enforce_mode, monkeypatch
):
    monkeypatch.setitem(sys.modules, "app.chat_errors", None)

    result = asyncio.run(host_save_note("still works", chat_id=VALID_ID))

    assert result["ok"] is True


def test_gate_survives_chat_identity_without_the_enforce_helper(
    host_workspace, enforce_mode, monkeypatch
):
    stub = types.ModuleType("app.chat_identity")  # no is_enforcing attribute
    monkeypatch.setitem(sys.modules, "app.chat_identity", stub)

    gated = host_read_file("note.txt")

    assert gated["error"]["code"] == "E6"

    (host_workspace / "fallback.txt").write_text("data\n")
    allowed = host_read_file("fallback.txt", chat_id=VALID_ID)

    assert allowed["ok"] is True


# ------------------------------------------------------------ structural wire


def test_registry_matches_the_host_tools_surface():
    assert set(TOOL_FUNCTIONS) == set(HOST_TOOLS)


def test_every_non_exempt_host_tool_accepts_a_chat_id():
    for name, func in TOOL_FUNCTIONS.items():
        if name in BIND_EXEMPT_TOOLS:
            continue
        parameters = inspect.signature(func).parameters
        assert "chat_id" in parameters, f"{name} lost its chat_id parameter"
