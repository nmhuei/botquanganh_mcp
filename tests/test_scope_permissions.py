"""Wave 1A: scoped permissions + file-operation hardening.

Every behavior under test is inert by default: with no new environment keys
set, path authorization must behave exactly like the single-workspace policy
that preceded it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import app.config
import app.host.files as files_module
from app.host.files import (
    append_text_file,
    list_directory,
    make_directory,
    read_text_file,
    replace_text_in_file,
    search_text,
    write_text_file,
)
from app.host.paths import resolve_host_path
from app.host.policy import inspect_host_command

REPO_ROOT = Path(__file__).resolve().parents[1]

_NEW_ENV_KEYS = (
    "HOST_READ_SCOPE",
    "HOST_WRITE_SCOPE",
    "HOST_READ_DENY_GLOBS",
    "ATTRIBUTION_MODE",
    "HOST_CHAT_WORKSPACES",
    "HOST_CHAT_ROOT",
    "HOST_CHAT_IDLE_ARCHIVE_HOURS",
    "HOST_CHAT_RETENTION_DAYS",
    "HOST_CHAT_MAX_WORKSPACES",
    "HOST_CHAT_QUOTA_MB",
    "HOST_CHAT_ISOLATE",
    "HOST_CHAT_RESUME_HINT_MINUTES",
    "HOST_CHAT_ROOT_MAX_GB",
    "HOST_CHAT_JOURNAL_MAX_BYTES",
    "SEARCH_TEXT_DEADLINE_SECONDS",
)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Inert-by-default configuration: scopes equal the workspace dir."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", ws.resolve())
    monkeypatch.setattr(app.config, "HOST_DEFAULT_DIR", ws.resolve())
    monkeypatch.setattr(app.config, "HOST_RESTRICT_TO_WORKSPACE", True)
    monkeypatch.setattr(app.config, "HOST_READ_SCOPE_SET", False)
    monkeypatch.setattr(app.config, "HOST_WRITE_SCOPE_SET", False)
    monkeypatch.setattr(app.config, "HOST_READ_SCOPE", ws.resolve())
    monkeypatch.setattr(app.config, "HOST_WRITE_SCOPE", ws.resolve())
    monkeypatch.setattr(app.config, "HOST_READ_DENY_GLOBS", [])
    return ws


@pytest.fixture
def split_scopes(workspace, monkeypatch):
    """READ_SCOPE and WRITE_SCOPE are explicit and disjoint."""
    read_dir = workspace.parent / "reads"
    write_dir = workspace.parent / "writes"
    read_dir.mkdir()
    write_dir.mkdir()
    monkeypatch.setattr(app.config, "HOST_READ_SCOPE_SET", True)
    monkeypatch.setattr(app.config, "HOST_WRITE_SCOPE_SET", True)
    monkeypatch.setattr(app.config, "HOST_READ_SCOPE", read_dir.resolve())
    monkeypatch.setattr(app.config, "HOST_WRITE_SCOPE", write_dir.resolve())
    return {"read": read_dir, "write": write_dir}


# ---------------------------------------------------------------------------
# Config parsing (subprocess-isolated because app.config loads once).
# ---------------------------------------------------------------------------


def _config_snapshot(extra_env: dict[str, str]) -> dict:
    code = (
        "import json, app.config as c; print(json.dumps({"
        "'ws': str(c.HOST_WORKSPACE_DIR),"
        "'read': str(c.HOST_READ_SCOPE),"
        "'write': str(c.HOST_WRITE_SCOPE),"
        "'read_set': c.HOST_READ_SCOPE_SET,"
        "'write_set': c.HOST_WRITE_SCOPE_SET,"
        "'deny': c.HOST_READ_DENY_GLOBS,"
        "'attribution': c.ATTRIBUTION_MODE,"
        "'chat_workspaces': c.HOST_CHAT_WORKSPACES,"
        "'chat_root': str(c.HOST_CHAT_ROOT),"
        "'idle_hours': c.HOST_CHAT_IDLE_ARCHIVE_HOURS,"
        "'retention': c.HOST_CHAT_RETENTION_DAYS,"
        "'max_ws': c.HOST_CHAT_MAX_WORKSPACES,"
        "'quota_mb': c.HOST_CHAT_QUOTA_MB,"
        "'isolate': c.HOST_CHAT_ISOLATE,"
        "'resume_hint': c.HOST_CHAT_RESUME_HINT_MINUTES,"
        "'root_gb': c.HOST_CHAT_ROOT_MAX_GB,"
        "'journal': c.HOST_CHAT_JOURNAL_MAX_BYTES,"
        "'search_deadline': c.SEARCH_TEXT_DEADLINE_SECONDS}))"
    )
    env = dict(os.environ)
    for key in _NEW_ENV_KEYS:
        env.pop(key, None)
    env.update({key: str(value) for key, value in extra_env.items()})
    proc = subprocess.run(  # nosec B603
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_new_settings_default_to_workspace_and_off():
    snap = _config_snapshot({})
    assert snap["read"] == snap["ws"]
    assert snap["write"] == snap["ws"]
    assert snap["read_set"] is False
    assert snap["write_set"] is False
    assert snap["deny"] == []
    assert snap["attribution"] == "off"
    assert snap["chat_workspaces"] is False
    assert snap["chat_root"] == str(Path.home() / "Downloads" / "bqa-workspaces")
    assert snap["idle_hours"] == 72
    assert snap["retention"] == 30
    assert snap["max_ws"] == 128
    assert snap["quota_mb"] == 2048
    assert snap["isolate"] is False
    assert snap["resume_hint"] == 30
    assert snap["root_gb"] == 24.0
    assert snap["journal"] == 8388608
    assert snap["search_deadline"] == 15.0


def test_new_settings_parse_explicit_environment(tmp_path):
    relative_scope = tmp_path / "relscope"
    chat_root = tmp_path / "chats"
    snap = _config_snapshot(
        {
            "HOST_READ_SCOPE": "scoped-reads",
            "HOST_WRITE_SCOPE": str(tmp_path / "abs-write"),
            "HOST_READ_DENY_GLOBS": " *.pem , secrets/* ,,",
            "ATTRIBUTION_MODE": "strict",
            "HOST_CHAT_WORKSPACES": "true",
            "HOST_CHAT_ROOT": str(chat_root),
            "HOST_CHAT_IDLE_ARCHIVE_HOURS": "1",
            "HOST_CHAT_RETENTION_DAYS": "2",
            "HOST_CHAT_MAX_WORKSPACES": "3",
            "HOST_CHAT_QUOTA_MB": "4",
            "HOST_CHAT_ISOLATE": "true",
            "HOST_CHAT_RESUME_HINT_MINUTES": "5",
            "HOST_CHAT_ROOT_MAX_GB": "6.5",
            "HOST_CHAT_JOURNAL_MAX_BYTES": "1024",
            "SEARCH_TEXT_DEADLINE_SECONDS": "2.5",
        }
    )
    assert snap["read"] == str((app.config.BASE_DIR / "scoped-reads").resolve())
    assert snap["write"] == str((tmp_path / "abs-write").resolve())
    assert snap["read_set"] is True
    assert snap["write_set"] is True
    assert snap["deny"] == ["*.pem", "secrets/*"]
    assert snap["attribution"] == "strict"
    assert snap["chat_workspaces"] is True
    assert snap["chat_root"] == str(chat_root)
    assert snap["idle_hours"] == 1
    assert snap["retention"] == 2
    assert snap["max_ws"] == 3
    assert snap["quota_mb"] == 4
    assert snap["isolate"] is True
    assert snap["resume_hint"] == 5
    assert snap["root_gb"] == 6.5
    assert snap["journal"] == 1024
    assert snap["search_deadline"] == 2.5
    assert not relative_scope.exists()


def test_invalid_attribution_mode_is_rejected():
    env = dict(os.environ)
    for key in _NEW_ENV_KEYS:
        env.pop(key, None)
    env["ATTRIBUTION_MODE"] = "loud"
    proc = subprocess.run(  # nosec B603
        [sys.executable, "-c", "import app.config"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=120,
    )
    assert proc.returncode != 0
    assert "ATTRIBUTION_MODE" in proc.stderr


# ---------------------------------------------------------------------------
# Scope matrix.
# ---------------------------------------------------------------------------


def test_reads_allowed_under_either_scope(split_scopes):
    read_file = split_scopes["read"] / "doc.txt"
    write_file = split_scopes["write"] / "doc.txt"
    read_file.write_text("readable", encoding="utf-8")
    write_file.write_text("also readable", encoding="utf-8")
    assert read_text_file(str(read_file))["content"] == "readable"
    assert read_text_file(str(write_file))["content"] == "also readable"


def test_reads_blocked_outside_both_scopes(split_scopes):
    outside = split_scopes["read"].parent / "elsewhere"
    outside.mkdir()
    target = outside / "hidden.txt"
    target.write_text("nope", encoding="utf-8")
    with pytest.raises(PermissionError):
        read_text_file(str(target))
    with pytest.raises(PermissionError):
        list_directory(str(outside))


def test_write_blocked_inside_read_scope_but_outside_write_scope(split_scopes):
    read_only_file = split_scopes["read"] / "frozen.txt"
    read_only_file.write_text("keep me", encoding="utf-8")
    with pytest.raises(PermissionError):
        write_text_file(str(read_only_file), "overwrite")
    assert read_only_file.read_text(encoding="utf-8") == "keep me"
    with pytest.raises(PermissionError):
        replace_text_in_file(str(read_only_file), "keep", "drop")
    with pytest.raises(PermissionError):
        append_text_file(str(read_only_file), "more")
    with pytest.raises(PermissionError):
        make_directory(str(split_scopes["read"] / "newdir"))
    assert read_text_file(str(read_only_file))["content"] == "keep me"


def test_writes_allowed_under_write_scope(split_scopes):
    result = write_text_file(str(split_scopes["write"] / "made.txt"), "data")
    assert result["ok"] is True


def test_deny_glob_blocks_reads(split_scopes, monkeypatch):
    monkeypatch.setattr(app.config, "HOST_READ_DENY_GLOBS", ["*.secret"])
    blocked = split_scopes["read"] / "creds.secret"
    allowed = split_scopes["read"] / "plain.txt"
    blocked.write_text("hidden", encoding="utf-8")
    allowed.write_text("visible", encoding="utf-8")
    with pytest.raises(PermissionError, match="HOST_READ_DENY_GLOBS"):
        read_text_file(str(blocked))
    assert read_text_file(str(allowed))["content"] == "visible"


def test_deny_glob_blocks_absolute_paths_for_writes_too(workspace, monkeypatch):
    monkeypatch.setattr(app.config, "HOST_READ_DENY_GLOBS", [str(workspace / "*.env")])
    target = workspace / "prod.env"
    with pytest.raises(PermissionError, match="HOST_READ_DENY_GLOBS"):
        write_text_file(str(target), "KEY=value")


def test_resolve_host_path_rejects_unknown_mode(workspace):
    with pytest.raises(ValueError, match="mode"):
        resolve_host_path(".", mode="execute")


# ---------------------------------------------------------------------------
# Inert-default equivalence.
# ---------------------------------------------------------------------------


def test_defaults_replicate_single_workspace_behavior(workspace):
    target = workspace / "note.txt"
    result = write_text_file("note.txt", "hello world")
    assert result == {
        "ok": True,
        "path": "note.txt",
        "size_bytes": len(b"hello world"),
        "overwrote": False,
    }
    replaced = replace_text_in_file("note.txt", "world", "there")
    assert replaced == {"ok": True, "path": "note.txt", "replacement_count": 1}
    assert target.read_text(encoding="utf-8") == "hello there"

    assert read_text_file("note.txt")["content"] == "hello there"
    assert list_directory(".")["items"][0]["name"] == "note.txt"
    found = search_text("hello", path=".")
    assert found["truncated"] is False
    assert found["deadline_exceeded"] is False
    assert [hit["path"] for hit in found["results"]] == ["note.txt"]

    outside = workspace.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    with pytest.raises(PermissionError, match="HOST_WORKSPACE_DIR"):
        read_text_file(str(outside))
    with pytest.raises(PermissionError):
        write_text_file(str(outside), "x")

    link = workspace / "escape"
    link.symlink_to(outside)
    with pytest.raises(PermissionError):
        read_text_file("escape")


def test_defaults_keep_unrestricted_mode_when_no_new_keys(workspace, monkeypatch):
    monkeypatch.setattr(app.config, "HOST_RESTRICT_TO_WORKSPACE", False)
    outside = workspace.parent / "free.txt"
    write_text_file(str(outside), "allowed")
    assert read_text_file(str(outside))["content"] == "allowed"


def test_default_recursive_rm_policy_unchanged(workspace):
    inside = workspace / "sub"
    inside.mkdir()
    assert inspect_host_command(f"rm -rf '{inside}'")["allowed"] is True
    outside = workspace.parent / "victim"
    blocked = inspect_host_command(f"rm -rf '{outside}'")
    assert blocked["allowed"] is False
    assert blocked["rule"] == "recursive_remove_outside_workspace"
    assert "HOST_WORKSPACE_DIR" in blocked["message"]


def test_recursive_rm_requires_write_scope(split_scopes):
    read_target = split_scopes["read"] / "archive"
    read_target.mkdir()
    blocked = inspect_host_command(f"rm -rf '{read_target}'")
    assert blocked["allowed"] is False
    assert blocked["rule"] == "recursive_remove_outside_workspace"
    assert "HOST_WRITE_SCOPE" in blocked["message"]

    write_target = split_scopes["write"] / "scratch"
    write_target.mkdir()
    assert inspect_host_command(f"rm -rf '{write_target}'")["allowed"] is True

    beyond = split_scopes["read"].parent / "unreachable"
    assert inspect_host_command(f"rm -rf '{beyond}'")["allowed"] is False


# ---------------------------------------------------------------------------
# Crash-atomic replacement.
# ---------------------------------------------------------------------------


def test_replace_roundtrip_preserves_content_and_shape(workspace):
    target = workspace / "notes.txt"
    target.write_text("alpha beta", encoding="utf-8")
    result = replace_text_in_file(str(target), "beta", "BETA")
    assert result == {
        "ok": True,
        "path": "notes.txt",
        "replacement_count": 1,
    }
    assert target.read_text(encoding="utf-8") == "alpha BETA"


def test_failed_swap_keeps_original_and_removes_temp(workspace, monkeypatch):
    target = workspace / "precious.txt"
    original = "do not lose me"
    target.write_text(original, encoding="utf-8")

    def exploding_replace(src, dst):
        raise OSError("simulated crash between temp write and swap")

    real_replace = files_module.os.replace
    monkeypatch.setattr(files_module.os, "replace", exploding_replace)
    with pytest.raises(OSError, match="simulated crash"):
        replace_text_in_file(str(target), "lose", "save")
    # Restore immediately (instead of undo()) so later steps run unpatched.
    monkeypatch.setattr(files_module.os, "replace", real_replace)

    assert target.read_text(encoding="utf-8") == original
    assert list(workspace.glob(".*.bqa-tmp-*")) == []

    # The operation stays usable after a failed swap attempt.
    replace_text_in_file(str(target), "lose", "save")
    assert target.read_text(encoding="utf-8") == "do not save me"
    assert list(workspace.glob(".*.bqa-tmp-*")) == []


def test_concurrent_disjoint_replaces_do_not_lose_updates(workspace):
    target = workspace / "shared.txt"
    target.write_text("alpha beta", encoding="utf-8")
    barrier = threading.Barrier(2)

    def replace(old: str, new: str) -> None:
        barrier.wait(timeout=5)
        replace_text_in_file(str(target), old, new)

    threads = [
        threading.Thread(target=replace, args=("alpha", "ALPHA")),
        threading.Thread(target=replace, args=("beta", "BETA")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert set(target.read_text(encoding="utf-8").split()) == {"ALPHA", "BETA"}


def test_replace_preserves_file_mode(workspace):
    target = workspace / "script.sh"
    target.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    target.chmod(0o755)
    replace_text_in_file(str(target), "hi", "bye")
    assert target.read_text(encoding="utf-8").endswith("echo bye\n")
    assert target.stat().st_mode & 0o777 == 0o755


def test_replace_rejects_missing_needle_without_touching_file(workspace):
    target = workspace / "stable.txt"
    target.write_text("unchanged", encoding="utf-8")
    with pytest.raises(ValueError, match="not found"):
        replace_text_in_file(str(target), "absent", "x")
    assert target.read_text(encoding="utf-8") == "unchanged"


# ---------------------------------------------------------------------------
# Search deadline.
# ---------------------------------------------------------------------------


@pytest.fixture
def search_tree(workspace):
    for index in range(40):
        directory = workspace / f"batch{index // 10}"
        directory.mkdir(exist_ok=True)
        (directory / f"file{index}.txt").write_text(f"needle {index}\n", encoding="utf-8")
    return workspace


def test_zero_deadline_returns_partial_promptly(search_tree):
    started = time.monotonic()
    result = search_text("needle", path=str(search_tree), deadline_seconds=0)
    elapsed = time.monotonic() - started

    assert result["ok"] is True
    assert result["deadline_exceeded"] is True
    assert result["truncated"] is True
    # The deadline fires before any file gets opened.
    assert result["scanned_files"] == 0
    assert result["results"] == []
    assert elapsed < 10


def test_search_deadline_defaults_from_config(search_tree, monkeypatch):
    monkeypatch.setattr(app.config, "SEARCH_TEXT_DEADLINE_SECONDS", 0.0)
    result = search_text("needle", path=str(search_tree))
    assert result["deadline_exceeded"] is True
    assert result["truncated"] is True


def test_search_within_deadline_completes(search_tree):
    result = search_text("needle", path=str(search_tree), deadline_seconds=30)
    assert result["deadline_exceeded"] is False
    assert result["truncated"] is False
    assert len(result["results"]) == 40
