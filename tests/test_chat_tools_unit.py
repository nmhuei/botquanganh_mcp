"""Unit tests for the chat workspace error catalog and MCP tool bodies."""

import asyncio
import errno
import json
import re
import sys
import types
from datetime import datetime

import pytest

import app.config
from app.chat_errors import (
    CHAT_ERROR_CATALOG,
    CHAT_ID_PATTERN,
    ChatCatalogError,
    chat_error_payload,
    internal_error_payload,
    to_tool_error,
    validate_chat_id,
)
from app.tools.workspace_tools import host_save_note, host_workspace_bind


@pytest.fixture
def chat_root(tmp_path, monkeypatch):
    monkeypatch.setattr(app.config, "HOST_CHAT_ROOT", str(tmp_path), raising=False)
    monkeypatch.setattr(app.config, "ATTRIBUTION_MODE", "off", raising=False)
    return tmp_path


@pytest.fixture
def workspaces_enabled(monkeypatch):
    monkeypatch.setattr(app.config, "HOST_CHAT_WORKSPACES", True, raising=False)


@pytest.fixture
def no_workspace_infra(monkeypatch):
    # A None entry in sys.modules makes the lazy import raise ImportError.
    monkeypatch.setitem(sys.modules, "app.chat_workspace", None)


def install_fake_workspace_module(monkeypatch, tmp_path, calls=None, shape="attr"):
    recorded_calls = calls if calls is not None else []
    roots = []

    class FakeWorkspaceManager:
        def __init__(self, root):
            self.root = root
            roots.append(root)

        def create_or_bind(self, chat_id=None, **kwargs):
            target = chat_id or kwargs.get("label") or "abcdef"
            recorded_calls.append(target)
            path = tmp_path / "chats" / target
            if shape == "dict":
                return {"path": str(path), "chat_id": target}
            return types.SimpleNamespace(
                path=path,
                created=True,
                resumed_hint=None,
                chat_id=target,
                session_token="sec_test_token_123",
            )

    module = types.ModuleType("app.chat_workspace")
    module.WorkspaceManager = FakeWorkspaceManager
    monkeypatch.setitem(sys.modules, "app.chat_workspace", module)
    return module


# ---------------------------------------------------------------- catalog


ALL_FORMAT_FIELDS = {
    "chat_id": "abc",
    "count": 3,
    "limit": 5,
    "used_bytes": 10,
    "quota_bytes": 20,
    "free_bytes": 1,
    "required_bytes": 2,
    "path": "/tmp/ws",
}


def test_every_catalog_code_formats_into_the_error_envelope():
    for code, entry in CHAT_ERROR_CATALOG.items():
        payload = chat_error_payload(code, **ALL_FORMAT_FIELDS)
        assert payload["ok"] is False
        error = payload["error"]
        assert error["code"] == code
        assert error["name"] == entry.name
        assert error["suggestion"]
        assert "\n" not in error["message"], entry.name
        assert "?" not in error["message"], entry.name


def test_missing_format_fields_degrade_to_placeholders_instead_of_raising():
    for code in CHAT_ERROR_CATALOG:
        payload = chat_error_payload(code)
        assert payload["error"]["message"]
        assert payload["error"]["code"] == code


def test_invalid_chat_id_copy_never_reaches_the_message():
    payload = chat_error_payload("E1", chat_id="<script>alert(1)</script>")
    assert "<script>" not in payload["error"]["message"]
    assert "alert" not in payload["error"]["message"]


@pytest.mark.parametrize(
    "value",
    ["abcdef", "a.b-c_d1", "user-123.chat", "A" * 64],
)
def test_validate_chat_id_accepts_safe_ids(value):
    assert validate_chat_id(value) == value


@pytest.mark.parametrize(
    "value",
    ["", "abc12", ".hidden", "a"*5, " leading", "trailing ",
     "../escape", "a/b", "a b", "a\tb", "x" * 65, "café"],
)
def test_validate_chat_id_rejects_unsafe_ids(value):
    with pytest.raises(ChatCatalogError) as excinfo:
        validate_chat_id(value)
    assert excinfo.value.code == "E1"


def test_chat_id_pattern_stays_in_sync_with_chat_workspace():
    workspace_module = pytest.importorskip("app.chat_workspace")
    assert CHAT_ID_PATTERN.pattern == workspace_module.CHAT_ID_PATTERN.pattern


def test_validate_chat_id_rejects_non_string_types():
    for value in (None, 7, b"abc", ["a"]):
        with pytest.raises(ChatCatalogError) as excinfo:
            validate_chat_id(value)
        assert excinfo.value.code == "E1"


# ---------------------------------------------------------- to_tool_error


def make_domain_exception_module():
    module = types.ModuleType("app.chat_workspace")

    class InvalidChatIdError(Exception):
        pass

    class WorkspaceLimitError(Exception):
        pass

    class QuotaExceededError(Exception):
        pass

    class WorkspaceRootFullError(Exception):
        pass

    class SquatDetectedError(Exception):
        pass

    module.InvalidChatIdError = InvalidChatIdError
    module.WorkspaceLimitError = WorkspaceLimitError
    module.QuotaExceededError = QuotaExceededError
    module.WorkspaceRootFullError = WorkspaceRootFullError
    module.SquatDetectedError = SquatDetectedError
    expected = {
        InvalidChatIdError: "E1",
        WorkspaceLimitError: "E2",
        QuotaExceededError: "E3",
        WorkspaceRootFullError: "E4",
        SquatDetectedError: "E5",
    }
    return module, expected


def test_to_tool_error_maps_domain_exceptions_onto_catalog_codes(monkeypatch):
    module, expected = make_domain_exception_module()
    with monkeypatch.context() as patch:
        patch.setitem(sys.modules, "app.chat_workspace", module)
        for exc_class, code in expected.items():
            payload = to_tool_error(exc_class("boom"))
            assert payload["ok"] is False
            assert payload["error"]["code"] == code


def test_to_tool_error_pulls_validated_fields_from_domain_exception(monkeypatch):
    module, _ = make_domain_exception_module()
    exc = module.QuotaExceededError("over quota")
    exc.chat_id = "abcdef"
    exc.used_bytes = 30
    exc.quota_bytes = 20
    with monkeypatch.context() as patch:
        patch.setitem(sys.modules, "app.chat_workspace", module)
        payload = to_tool_error(exc)
    message = payload["error"]["message"]
    assert payload["error"]["code"] == "E3"
    assert "abcdef" in message
    assert "30" in message
    assert "20" in message


def test_to_tool_error_passes_catalog_errors_through():
    payload = to_tool_error(ChatCatalogError("E2", count=4, limit=8))
    assert payload["error"]["code"] == "E2"
    assert "4 of 8" in payload["error"]["message"]


def test_to_tool_error_maps_enospc_onto_root_full_without_infra(no_workspace_infra):
    payload = to_tool_error(OSError(errno.ENOSPC, "No space left on device"))
    assert payload["error"]["code"] == "E4"


def test_to_tool_error_name_fragment_backstop_without_infra(no_workspace_infra):
    class OddSquatPathError(Exception):
        pass

    payload = to_tool_error(OddSquatPathError("occupied"))
    assert payload["error"]["code"] == "E5"


def test_to_tool_error_unknown_exception_falls_back_to_internal():
    payload = to_tool_error(RuntimeError("boom"))
    assert payload == internal_error_payload()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INTERNAL"


# ---------------------------------------------------- host_workspace_bind


@pytest.mark.parametrize("shape", ["attr", "dict"])
def test_bind_success_returns_absolute_path_lines(
    chat_root, workspaces_enabled, monkeypatch, shape
):
    calls = []
    install_fake_workspace_module(monkeypatch, chat_root, calls=calls, shape=shape)

    result = asyncio.run(host_workspace_bind("abcdef"))

    assert result["ok"] is True
    expected = str((chat_root / "chats" / "abcdef").resolve())
    assert result["workspace"] == expected
    assert result["chat_id"] == "abcdef"
    assert result["lines"][0] == expected
    hints = result["lines"][1:]
    assert 2 <= len(hints) <= 3
    assert all(isinstance(line, str) and line for line in hints)
    assert calls == ["abcdef"]


def test_bind_invalid_chat_id_returns_structured_e1(chat_root, monkeypatch):
    calls = []
    install_fake_workspace_module(monkeypatch, chat_root, calls=calls)

    result = asyncio.run(host_workspace_bind(chat_id="../escape"))

    assert result["ok"] is False
    assert result["error"]["code"] == "E1"
    assert calls == []


def test_bind_wraps_unknown_manager_errors_as_internal(
    chat_root, workspaces_enabled, monkeypatch
):
    module = types.ModuleType("app.chat_workspace")
    calls = []

    class ExplodingManager:
        def __init__(self, root):
            self.root = root

        def create_or_bind(self, chat_id=None, **kwargs):
            calls.append(chat_id or kwargs.get("label"))
            raise RuntimeError("workspace manager exploded")

    module.WorkspaceManager = ExplodingManager
    monkeypatch.setitem(sys.modules, "app.chat_workspace", module)

    result = asyncio.run(host_workspace_bind(chat_id="abcdef"))

    assert result["ok"] is False
    assert calls == ["abcdef"]
    assert result["error"]["code"] == "INTERNAL"


def test_bind_disabled_flag_returns_not_available_without_touching_infra(
    chat_root, monkeypatch
):
    calls = []
    install_fake_workspace_module(monkeypatch, chat_root, calls=calls)
    monkeypatch.setattr(app.config, "HOST_CHAT_WORKSPACES", False, raising=False)

    result = asyncio.run(host_workspace_bind("abcdef"))

    assert result["ok"] is False
    assert isinstance(result, dict)
    assert result["error"]["code"] == "NOT_AVAILABLE"
    assert calls == []


def test_bind_missing_infra_returns_not_available_instead_of_raising(
    chat_root, workspaces_enabled, no_workspace_infra
):
    result = asyncio.run(host_workspace_bind("abcdef"))

    assert result["ok"] is False
    assert result["error"]["code"] == "NOT_AVAILABLE"


# ---------------------------------------------------------- host_save_note


ISO_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:\d{2}|Z)$")


def read_single_note(path):
    content = path.read_text(encoding="utf-8")
    assert content.endswith("\n")
    lines = content.splitlines()
    assert len(lines) == 1
    timestamp, _, note = lines[0].partition(" ")
    assert ISO_PREFIX.match(timestamp), timestamp
    datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return note


def test_save_note_without_chat_id_writes_shared_log(chat_root, no_workspace_infra):
    result = asyncio.run(host_save_note("hello world"))

    log_file = chat_root / "notes" / "log.txt"
    assert result["ok"] is True
    assert result["path"] == str(log_file)
    assert read_single_note(log_file) == "hello world"


def test_save_note_appends_one_line_per_call(chat_root, no_workspace_infra):
    asyncio.run(host_save_note("first"))
    asyncio.run(host_save_note("second"))

    lines = (chat_root / "notes" / "log.txt").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0].endswith(" first")
    assert lines[1].endswith(" second")


def test_save_note_keeps_one_entry_per_line(chat_root, no_workspace_infra):
    result = asyncio.run(host_save_note("alpha\nbeta\r\ngamma"))
    log_file = chat_root / "notes" / "log.txt"

    assert result["ok"] is True
    assert read_single_note(log_file) == "alpha beta gamma"


@pytest.mark.parametrize("text", ["", "   \n\t  "])
def test_save_note_rejects_blank_text_without_creating_files(
    chat_root, no_workspace_infra, text
):
    result = asyncio.run(host_save_note(text))

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert not (chat_root / "notes").exists()


def test_save_note_invalid_chat_id_returns_structured_e1(chat_root):
    result = asyncio.run(host_save_note("hi", chat_id="../escape"))

    assert result["ok"] is False
    assert result["error"]["code"] == "E1"
    # Copy-safety: the raw rejected id never reaches the message.
    assert "../escape" not in result["error"]["message"]
    assert not (chat_root / "notes").exists()
    assert not (chat_root / "escape").exists()


def test_save_note_with_chat_id_uses_bound_workspace(
    chat_root, workspaces_enabled, monkeypatch
):
    calls = []
    install_fake_workspace_module(monkeypatch, chat_root, calls=calls)

    result = asyncio.run(host_save_note("bound note", chat_id="abcdef"))

    log_file = chat_root / "chats" / "abcdef" / "notes" / "log.txt"
    assert result["ok"] is True
    assert result["path"] == str(log_file)
    assert read_single_note(log_file) == "bound note"
    assert calls == ["abcdef"]


def test_save_note_falls_back_to_conventional_directory_without_infra(
    chat_root, workspaces_enabled, no_workspace_infra
):
    result = asyncio.run(host_save_note("offline note", chat_id="abcdef"))

    log_file = chat_root / "abcdef" / "notes" / "log.txt"
    assert result["ok"] is True
    assert result["path"] == str(log_file)
    assert read_single_note(log_file) == "offline note"


def test_save_note_disabled_flag_skips_binding_for_known_chats(
    chat_root, monkeypatch, no_workspace_infra
):
    calls = []
    install_fake_workspace_module(monkeypatch, chat_root, calls=calls)
    monkeypatch.setattr(app.config, "HOST_CHAT_WORKSPACES", False, raising=False)

    result = asyncio.run(host_save_note("flagged", chat_id="abcdef"))

    assert result["ok"] is True
    assert calls == []
    assert (chat_root / "abcdef" / "notes" / "log.txt").exists()


# ------------------------------------------------- real chat_workspace infra


def _real_workspace_env(tmp_path, monkeypatch):
    pytest.importorskip("app.chat_workspace")
    monkeypatch.setattr(app.config, "HOST_CHAT_WORKSPACES", True, raising=False)
    monkeypatch.setattr(app.config, "HOST_CHAT_ROOT", str(tmp_path), raising=False)
    monkeypatch.setattr(app.config, "ATTRIBUTION_MODE", "off", raising=False)


def test_bind_against_real_infrastructure_creates_metadata(tmp_path, monkeypatch):
    _real_workspace_env(tmp_path, monkeypatch)

    result = asyncio.run(host_workspace_bind(chat_id="integration"))

    workspace_dir = tmp_path / "integration"
    assert result["ok"] is True
    assert result["workspace"] == str(workspace_dir)
    assert result["created"] is True
    assert (workspace_dir / "meta.json").exists()


def test_bind_capacity_error_maps_onto_e2(tmp_path, monkeypatch):
    _real_workspace_env(tmp_path, monkeypatch)
    monkeypatch.setattr(app.config, "HOST_CHAT_MAX_WORKSPACES", 1, raising=False)
    asyncio.run(host_workspace_bind(chat_id="first1"))

    result = asyncio.run(host_workspace_bind(chat_id="second"))

    assert result["ok"] is False
    assert result["error"]["code"] == "E2"
    # Copy-safety: the raw manager error text never reaches the message.
    assert "max_workspaces" not in result["error"]["message"]
    assert str(tmp_path) not in result["error"]["message"]


def test_bind_foreign_owned_directory_maps_onto_e5(tmp_path, monkeypatch):
    pytest.importorskip("app.chat_workspace")
    from app.chat_workspace import WORKSPACE_SCHEMA

    _real_workspace_env(tmp_path, monkeypatch)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    meta = {
        "chat_id": "otherchat",
        "created_at": "2026-01-01T00:00:00+00:00",
        "schema": WORKSPACE_SCHEMA,
        "next_seq": 1,
    }
    (foreign / "meta.json").write_text(json.dumps(meta) + "\n", encoding="utf-8")

    result = asyncio.run(host_workspace_bind(chat_id="foreign"))

    assert result["ok"] is False
    assert result["error"]["code"] == "E5"


def test_save_note_lands_in_real_bound_workspace(tmp_path, monkeypatch):
    _real_workspace_env(tmp_path, monkeypatch)
    asyncio.run(host_workspace_bind(chat_id="integration"))

    note = asyncio.run(host_save_note("real note", chat_id="integration"))
    log_file = tmp_path / "integration" / "notes" / "log.txt"

    assert note["ok"] is True
    assert note["path"] == str(log_file)
    assert read_single_note(log_file) == "real note"
