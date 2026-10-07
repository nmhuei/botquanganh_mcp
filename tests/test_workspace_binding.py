"""Unit tests for the thread-safe in-memory workspace binding registry."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.workspace_binding import (
    clear_workspace_bindings,
    forget_workspace_binding,
    has_workspace_binding,
    register_workspace_binding,
    validate_workspace_binding,
)


@pytest.fixture(autouse=True)
def clean_registry():
    clear_workspace_bindings()
    yield
    clear_workspace_bindings()


def test_registry_initially_empty(tmp_path):
    assert not has_workspace_binding(tmp_path, "cw-20261007-session-01")
    assert not validate_workspace_binding(tmp_path, "cw-20261007-session-01")


def test_register_and_has_binding(tmp_path):
    chat_id = "cw-20261007-session-01"
    created_at = "2026-10-07T12:00:00Z"
    register_workspace_binding(tmp_path, chat_id, created_at)
    assert has_workspace_binding(tmp_path, chat_id)


def test_validate_binding_with_matching_meta(tmp_path):
    chat_id = "cw-20261007-session-01"
    created_at = "2026-10-07T12:00:00Z"
    ws_dir = tmp_path / chat_id
    ws_dir.mkdir(parents=True)
    (ws_dir / "meta.json").write_text(json.dumps({"chat_id": chat_id, "created_at": created_at}))

    register_workspace_binding(tmp_path, chat_id, created_at)
    assert validate_workspace_binding(tmp_path, chat_id)


def test_validate_binding_fails_if_meta_missing(tmp_path):
    chat_id = "cw-20261007-session-01"
    created_at = "2026-10-07T12:00:00Z"
    register_workspace_binding(tmp_path, chat_id, created_at)
    # ws_dir does not exist on disk
    assert not validate_workspace_binding(tmp_path, chat_id)
    # Stale binding should be cleaned up
    assert not has_workspace_binding(tmp_path, chat_id)


def test_validate_binding_fails_if_meta_incarnation_mismatch(tmp_path):
    chat_id = "cw-20261007-session-01"
    ws_dir = tmp_path / chat_id
    ws_dir.mkdir(parents=True)
    (ws_dir / "meta.json").write_text(json.dumps({"chat_id": chat_id, "created_at": "2026-10-07T15:00:00Z"}))

    register_workspace_binding(tmp_path, chat_id, "2026-10-07T12:00:00Z")
    assert not validate_workspace_binding(tmp_path, chat_id)
    assert not has_workspace_binding(tmp_path, chat_id)


def test_forget_binding(tmp_path):
    chat_id = "cw-20261007-session-01"
    register_workspace_binding(tmp_path, chat_id, "2026-10-07T12:00:00Z")
    assert has_workspace_binding(tmp_path, chat_id)
    forget_workspace_binding(tmp_path, chat_id)
    assert not has_workspace_binding(tmp_path, chat_id)


def test_concurrent_registry_access(tmp_path):
    def worker(idx: int):
        cid = f"cw-20261007-session-{idx:02d}"
        created = f"2026-10-07T12:00:{idx:02d}Z"
        register_workspace_binding(tmp_path, cid, created)
        assert has_workspace_binding(tmp_path, cid)
        forget_workspace_binding(tmp_path, cid)
        assert not has_workspace_binding(tmp_path, cid)

    with ThreadPoolExecutor(max_workers=10) as executor:
        list(executor.map(worker, range(50)))
