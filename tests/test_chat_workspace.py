import json
import os
import sys
import threading
import time
import types

import pytest

import app.chat_workspace as cw
import app.config

VALID_IDS = [
    "abcdef",
    "aB0-._z",
    "abcde.f",
    "x" * 64,
    "A1b2C3d4E5",
]

INVALID_IDS = [
    "",
    "abcde",
    "x" * 65,
    "_bcdef",
    ".bcdef",
    "abcd e",
    "ab cd",
    "ábcdef",
    "abc\ndef",
    "abc#ef",
]


@pytest.fixture()
def manager(tmp_path):
    return cw.WorkspaceManager(tmp_path / "chats", bind_wait_seconds=0.25)


# ---------------------------------------------------------------------------
# Chat-id matrix.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("chat_id", VALID_IDS)
def test_valid_ids_accepted(chat_id):
    assert cw.validate_chat_id(chat_id) == chat_id
    assert cw.is_valid_chat_id(chat_id) is True


@pytest.mark.parametrize("chat_id", INVALID_IDS)
def test_invalid_ids_rejected(chat_id):
    with pytest.raises(ValueError):
        cw.validate_chat_id(chat_id)
    assert cw.is_valid_chat_id(chat_id) is False


@pytest.mark.parametrize("value", [None, 123456, ["abcdef"], b"abcdef"])
def test_non_string_ids_rejected(value):
    assert cw.is_valid_chat_id(value) is False


def test_compatible_sibling_validator_is_used(monkeypatch):
    seen = []

    def validator(chat_id):
        seen.append(chat_id)
        return cw.CHAT_ID_PATTERN.fullmatch(str(chat_id)) is not None

    module = types.ModuleType("app.chat_identity")
    module.validate_chat_id = validator
    monkeypatch.setitem(sys.modules, "app.chat_identity", module)

    assert cw.is_valid_chat_id("abcdef") is True
    assert "abcdef" in seen
    # The verbatim pattern floor rejects this before the sibling is consulted.
    assert cw.is_valid_chat_id("abc") is False
    assert "abc" not in seen


def test_incompatible_sibling_validator_is_ignored(monkeypatch):
    module = types.ModuleType("app.chat_identity")
    module.is_valid_chat_id = lambda chat_id: True
    monkeypatch.setitem(sys.modules, "app.chat_identity", module)

    assert cw.is_valid_chat_id("abc") is False
    assert cw.is_valid_chat_id("abcdef") is True


def test_raising_sibling_validator_falls_back_locally(monkeypatch):
    def boom(chat_id):
        raise RuntimeError("sibling exploded")

    module = types.ModuleType("app.chat_identity")
    module.validate_chat_id = boom
    monkeypatch.setitem(sys.modules, "app.chat_identity", module)

    assert cw.is_valid_chat_id("abcdef") is True
    assert cw.is_valid_chat_id("abc") is False


def test_missing_sibling_module_uses_local_pattern():
    saved = sys.modules.pop("app.chat_identity", None)
    try:
        assert cw.is_valid_chat_id("abcdef") is True
        assert cw.is_valid_chat_id("abcde") is False
    finally:
        if saved is not None:
            sys.modules["app.chat_identity"] = saved


# ---------------------------------------------------------------------------
# Limits.
# ---------------------------------------------------------------------------


def test_limits_documented_defaults(monkeypatch):
    for key in (
        "HOST_CHAT_MAX_WORKSPACES",
        "HOST_CHAT_QUOTA_MB",
        "HOST_CHAT_ROOT_MAX_GB",
        "HOST_CHAT_JOURNAL_MAX_BYTES",
        "HOST_CHAT_IDLE_ARCHIVE_HOURS",
        "HOST_CHAT_RETENTION_DAYS",
        "HOST_CHAT_RESUME_HINT_MINUTES",
    ):
        monkeypatch.delattr(app.config, key, raising=False)
    limits = cw.read_limits()
    assert limits.max_workspaces == 128
    assert limits.quota_mb == 2048
    assert limits.root_max_gb == 24
    assert limits.journal_max_bytes == 8388608
    assert limits.idle_archive_hours == 72
    assert limits.retention_days == 30
    assert limits.resume_hint_minutes == 30


def test_limits_pick_up_config_attributes(monkeypatch):
    monkeypatch.setattr(app.config, "HOST_CHAT_RESUME_HINT_MINUTES", 5, raising=False)
    monkeypatch.setattr(app.config, "HOST_CHAT_JOURNAL_MAX_BYTES", 4096, raising=False)
    limits = cw.read_limits()
    assert limits.resume_hint_minutes == 5
    assert limits.journal_max_bytes == 4096


# ---------------------------------------------------------------------------
# Creation, binding, squat defense.
# ---------------------------------------------------------------------------


def test_create_layout_and_meta(manager, tmp_path):
    result = manager.create_or_bind("abcdef")
    assert result.created is True
    assert result.resumed_hint is None
    ws = tmp_path / "chats" / "abcdef"
    assert (ws / "journal.jsonl").exists()
    assert (ws / "STATE.md").exists()
    assert (ws / "notes").is_dir()
    meta = json.loads((ws / "meta.json").read_text(encoding="utf-8"))
    assert set(meta) == {"chat_id", "created_at", "schema", "next_seq"}
    assert meta["chat_id"] == "abcdef"
    assert meta["schema"] == 1
    assert meta["next_seq"] == 1


def test_bind_existing_workspace(manager):
    first = manager.create_or_bind("bind001")
    second = manager.create_or_bind("bind001")
    assert second.created is False
    assert second.path == first.path
    assert second.resumed_hint is not None


def test_resumed_hint_expires(manager, tmp_path):
    manager.create_or_bind("hint01")
    old = time.time() - 4 * 3600
    ws = tmp_path / "chats" / "hint01"
    os.utime(ws / "journal.jsonl", (old, old))
    os.utime(ws / "meta.json", (old, old))
    stale = manager.create_or_bind("hint01")
    assert stale.created is False
    assert stale.resumed_hint is None


def test_concurrent_create_exactly_one_winner(manager):
    barrier = threading.Barrier(2)
    results: dict[int, cw.BindResult] = {}

    def worker(tag):
        barrier.wait()
        results[tag] = manager.create_or_bind("race01")

    threads = [threading.Thread(target=worker, args=(tag,)) for tag in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(result.created for result in results.values()) == [False, True]
    paths = {result.path for result in results.values()}
    assert len(paths) == 1
    meta = json.loads((paths.pop() / "meta.json").read_text(encoding="utf-8"))
    assert meta["chat_id"] == "race01"


def test_squat_junk_meta_detected(manager, tmp_path):
    ws = tmp_path / "chats" / "squat1"
    ws.mkdir(parents=True)
    (ws / "meta.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(cw.SquatError):
        manager.create_or_bind("squat1")


def test_squat_missing_meta_detected(manager, tmp_path):
    (tmp_path / "chats" / "squat2").mkdir(parents=True)
    with pytest.raises(cw.SquatError):
        manager.create_or_bind("squat2")


def test_squat_meta_without_next_seq_detected(manager, tmp_path):
    ws = tmp_path / "chats" / "squat3"
    ws.mkdir(parents=True)
    (ws / "meta.json").write_text(
        json.dumps({"chat_id": "squat3", "schema": 1}), encoding="utf-8"
    )
    with pytest.raises(cw.SquatError):
        manager.create_or_bind("squat3")


def test_squat_foreign_owner_detected(manager):
    bound = manager.create_or_bind("owner1")
    (bound.path / "meta.json").write_text(
        json.dumps({"chat_id": "other9", "schema": 1, "next_seq": 1}),
        encoding="utf-8",
    )
    with pytest.raises(cw.SquatError):
        manager.create_or_bind("owner1")


def test_max_workspaces_enforced_but_binding_unaffected(monkeypatch, tmp_path):
    monkeypatch.setattr(app.config, "HOST_CHAT_MAX_WORKSPACES", 2, raising=False)
    mgr = cw.WorkspaceManager(tmp_path / "chats", bind_wait_seconds=0.25)
    mgr.create_or_bind("cap0001")
    mgr.create_or_bind("cap0002")
    with pytest.raises(cw.CapacityError):
        mgr.create_or_bind("cap0003")
    assert mgr.create_or_bind("cap0001").created is False


# ---------------------------------------------------------------------------
# Two-phase journal.
# ---------------------------------------------------------------------------


def test_append_records_have_contract_shape(manager):
    manager.create_or_bind("shape1")
    started = manager.append_op_started("shape1", "opS", "shell", {"cmd": "ls"})
    assert set(started) == {"seq", "ts", "type", "op", "kind", "payload"}
    assert started["seq"] == 1
    assert started["type"] == "op_started"
    result = manager.append_op_result("shape1", "opS", True, {"exit": 0})
    assert set(result) == {"seq", "ts", "type", "op", "ok", "payload"}
    assert result["seq"] == 2
    assert result["ok"] is True
    raw = (manager.root / "shape1" / "journal.jsonl").read_bytes()
    assert raw.endswith(b"\n")
    lines = raw.decode("utf-8").splitlines()
    assert len(lines) == 2


def test_pending_pairing_survives_restart(manager):
    manager.create_or_bind("pend01")
    manager.append_op_started("pend01", "opA", "shell", {"cmd": "ls"})
    manager.append_op_started("pend01", "opB", "run", {})

    pending = manager.pending_ops("pend01")
    assert [item["op"] for item in pending] == ["opA", "opB"]
    assert pending[0]["kind"] == "shell"

    fresh = cw.WorkspaceManager(manager.root, bind_wait_seconds=0.25)
    fresh.append_op_result("pend01", "opA", False, {"error": "boom"})
    remaining = fresh.pending_ops("pend01")
    assert [item["op"] for item in remaining] == ["opB"]


def test_result_after_restart_clears_pending(manager):
    manager.create_or_bind("pend02")
    manager.append_op_started("pend02", "opX", "run", {})
    fresh = cw.WorkspaceManager(manager.root, bind_wait_seconds=0.25)
    assert fresh.pending_ops("pend02")[0]["op"] == "opX"
    fresh.append_op_result("pend02", "opX", True, {})
    assert fresh.pending_ops("pend02") == []


def test_seq_persists_across_manager_instances(manager):
    manager.create_or_bind("seqp01")
    first = manager.append_op_started("seqp01", "op1", "run", {})
    fresh = cw.WorkspaceManager(manager.root, bind_wait_seconds=0.25)
    second = fresh.append_op_result("seqp01", "op1", True, {})
    assert first["seq"] == 1
    assert second["seq"] == 2
    meta = json.loads((manager.root / "seqp01" / "meta.json").read_text(encoding="utf-8"))
    assert meta["next_seq"] == 3


def test_torn_tail_repair_keeps_complete_lines(manager, tmp_path):
    manager.create_or_bind("torn001")
    manager.append_op_started("torn001", "op1", "run", {"n": 1})
    manager.append_op_result("torn001", "op1", True, {"out": "done"})
    journal = tmp_path / "chats" / "torn001" / "journal.jsonl"

    with journal.open("ab") as handle:
        handle.write(b'{"seq":99,"type":"op_star')
    assert journal.read_bytes().endswith(b'"op_star')

    events = manager.read_events("torn001")
    assert [event["seq"] for event in events] == [1, 2]
    assert journal.read_bytes().endswith(b"\n")

    third = manager.append_op_started("torn001", "op2", "run", {})
    assert third["seq"] == 3
    assert [event["seq"] for event in manager.read_events("torn001")] == [1, 2, 3]
    assert b'"op_star"' not in journal.read_bytes()


def test_large_string_payload_excerpted_not_dropped(manager):
    manager.create_or_bind("bigp01")
    record = manager.append_op_started(
        "bigp01", "opB", "run", {"stdout": "y" * 50000}
    )
    text = record["payload"]["stdout"]
    assert text.startswith("y" * 16384)
    assert text.endswith("...<truncated 33616 bytes>")
    stored = manager.read_events("bigp01")[0]
    assert stored["payload"]["stdout"] == text


def test_sanitize_payload_handles_nesting_and_scalars():
    assert cw.sanitize_payload("short") == "short"
    assert cw.sanitize_payload(42) == 42
    assert cw.sanitize_payload(None) is None
    out = cw.sanitize_payload({"a": ["z" * 50000], "b": {"c": "ok"}, "d": ("q" * 60000,)})
    assert out["a"][0].endswith("bytes>")
    assert out["d"][0].startswith("q" * 16384)
    assert out["b"] == {"c": "ok"}


# ---------------------------------------------------------------------------
# STATE.md rendering and rebuild.
# ---------------------------------------------------------------------------


def test_render_state_md_byte_deterministic():
    meta = {
        "next_seq": 5,
        "created_at": "2026-01-01T00:00:00+00:00",
        "schema": 1,
        "chat_id": "det001",
    }
    events = [
        {
            "seq": 2,
            "ts": "2026-01-01T00:02:00+00:00",
            "type": "op_result",
            "op": "op1",
            "kind": "run",
            "ok": True,
            "payload": {"k": 1},
        },
        {
            "seq": 1,
            "ts": "2026-01-01T00:01:00+00:00",
            "type": "op_started",
            "op": "op1",
            "kind": "run",
            "payload": {},
        },
    ]
    one = cw.render_state_md(meta, events)
    two = cw.render_state_md(meta, events)
    assert one == two
    assert one.endswith("\n")
    assert one.index("# Workspace State") < one.index("## Pending Operations")
    assert one.index("## Pending Operations") < one.index("## Events")
    assert "- chat_id: det001" in one
    assert "| 1 |" in one and "| true |" in one


def test_render_state_md_lists_pending_ops():
    meta = {"chat_id": "det002", "created_at": "2026-01-01T00:00:00+00:00", "next_seq": 2, "schema": 1}
    events = [
        {
            "seq": 1,
            "ts": "2026-01-01T00:01:00+00:00",
            "type": "op_started",
            "op": "stuck",
            "kind": "shell",
            "payload": {},
        }
    ]
    rendered = cw.render_state_md(meta, events)
    assert "- seq=1 op=stuck kind=shell started=2026-01-01T00:01:00+00:00" in rendered
    assert "| 1 | 2026-01-01T00:01:00+00:00 | op_started | stuck | shell |  |" in rendered


def test_rebuild_state_regenerates_from_journal(manager, tmp_path):
    manager.create_or_bind("reb001")
    manager.append_op_started("reb001", "opR", "shell", {"cmd": "id"})
    state_path = tmp_path / "chats" / "reb001" / "STATE.md"
    state_path.write_text("tampered content", encoding="utf-8")
    text = manager.rebuild_state("reb001")
    assert "tampered" not in text
    assert "opR" in text
    assert state_path.read_text(encoding="utf-8") == text


# ---------------------------------------------------------------------------
# Rotation.
# ---------------------------------------------------------------------------


def test_rotation_preserves_monotonic_seq(monkeypatch, tmp_path):
    monkeypatch.setattr(app.config, "HOST_CHAT_JOURNAL_MAX_BYTES", 512, raising=False)
    mgr = cw.WorkspaceManager(tmp_path / "chats", bind_wait_seconds=0.25)
    mgr.create_or_bind("rot001")
    for index in range(6):
        mgr.append_op_started("rot001", f"op{index}", "run", {"blob": "b" * 120})

    ws = tmp_path / "chats" / "rot001"
    archive_path = ws / "journal.jsonl.1"
    active_path = ws / "journal.jsonl"
    assert archive_path.exists()

    # Single-slot rotation replaces the previous .1; surviving records must
    # still be strictly increasing and continue into the active journal.
    archive = [json.loads(line) for line in archive_path.read_text(encoding="utf-8").splitlines()]
    active = [json.loads(line) for line in active_path.read_text(encoding="utf-8").splitlines()]
    assert archive and active
    assert max(event["seq"] for event in archive) < min(event["seq"] for event in active)

    events = mgr.read_events("rot001")
    seqs = [event["seq"] for event in events]
    assert seqs == sorted(set(seqs))
    assert seqs[-1] == 6

    meta = json.loads((ws / "meta.json").read_text(encoding="utf-8"))
    assert meta["next_seq"] == 7
    extra = mgr.append_op_result("rot001", "op5", True, {})
    assert extra["seq"] == 7


def test_rotation_only_on_started_ops(monkeypatch, tmp_path):
    monkeypatch.setattr(app.config, "HOST_CHAT_JOURNAL_MAX_BYTES", 500, raising=False)
    mgr = cw.WorkspaceManager(tmp_path / "chats", bind_wait_seconds=0.25)
    mgr.create_or_bind("rot002")
    mgr.append_op_started("rot002", "op1", "run", {"blob": "c" * 200})
    assert not (tmp_path / "chats" / "rot002" / "journal.jsonl.1").exists()
    big_result = mgr.append_op_result("rot002", "op1", True, {"blob": "c" * 400})
    assert big_result["seq"] == 2
    assert not (tmp_path / "chats" / "rot002" / "journal.jsonl.1").exists()
    stored = mgr.read_events("rot002")
    assert len(stored) == 2 and len(stored[1]["payload"]["blob"]) == 400
