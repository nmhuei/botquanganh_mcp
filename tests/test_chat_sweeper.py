"""Tests for the pure chat workspace lifecycle sweeper."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from app.chat_sweeper import (
    ARCHIVE_DIR_NAME,
    META_FILENAME,
    SweepLimits,
    apply_actions,
    plan_actions,
    run_sweep_once,
    scan,
)

_BYTES_PER_GIB = 1024**3


def _set_tree_mtime(top: Path, timestamp: float) -> None:
    for path in (top, *top.rglob("*")):
        os.utime(path, (timestamp, timestamp))


def _make_ws(
    root: Path,
    name: str,
    *,
    age_seconds: float = 0.0,
    size_bytes: int = 0,
    meta: str | None = "good",
) -> Path:
    ws = root / name
    ws.mkdir(parents=True)
    if meta == "good":
        (ws / META_FILENAME).write_text(
            json.dumps({"chat_id": name}), encoding="utf-8"
        )
    elif meta == "corrupt":
        (ws / META_FILENAME).write_text("{not json", encoding="utf-8")
    if size_bytes:
        (ws / "data.bin").write_bytes(b"x" * size_bytes)
    if age_seconds:
        _set_tree_mtime(ws, time.time() - age_seconds)
    return ws


def _snapshot(base: Path) -> list[str]:
    return sorted(str(p.relative_to(base)) for p in base.rglob("*"))


def _entry(inventory: list[dict], chat_id: str) -> dict:
    matches = [e for e in inventory if e["chat_id"] == chat_id]
    assert len(matches) == 1, f"expected exactly one entry for {chat_id}"
    return matches[0]


def test_scan_reports_workspaces_and_summarized_archive(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    _make_ws(root, "alpha", age_seconds=60, size_bytes=128)
    archive_dir = root / ARCHIVE_DIR_NAME
    archive_dir.mkdir()
    _make_ws(archive_dir, "old-one", age_seconds=120)

    inventory = scan(root)
    ids = sorted(e["chat_id"] for e in inventory)

    assert ids == ["alpha", "old-one"]
    active = _entry(inventory, "alpha")
    assert active["archived"] is False
    assert active["meta_ok"] is True
    assert active["size_bytes"] > 0
    assert isinstance(active["mtime"], float)
    archived = _entry(inventory, "old-one")
    assert archived["archived"] is True
    assert archived["size_bytes"] is None
    # The archive directory itself must never appear as a workspace.
    assert all(e["path"] != str(archive_dir) for e in inventory)


def test_scan_meta_flags(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    _make_ws(root, "good", meta="good")
    _make_ws(root, "corrupt", meta="corrupt")
    _make_ws(root, "missing", meta=None)

    inventory = scan(root)

    assert _entry(inventory, "good")["meta_ok"] is True
    assert _entry(inventory, "corrupt")["meta_ok"] is False
    assert _entry(inventory, "missing")["meta_ok"] is False


def test_idle_boundary_just_under_vs_just_over(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    hour = 3600.0
    _make_ws(root, "just-under", age_seconds=hour - 120)
    _make_ws(root, "just-over", age_seconds=hour + 120)

    inventory = scan(root)
    actions = plan_actions(
        inventory, SweepLimits(idle_archive_hours=1.0, max_workspaces=100)
    )

    assert [a["action"] for a in actions] == ["ARCHIVE_IDLE"]
    assert actions[0]["target"] == str(root / "just-over")

    results = apply_actions(actions, root, dry_run=False)
    assert results[0]["status"] == "archived"
    assert (root / ARCHIVE_DIR_NAME / "just-over").is_dir()
    assert (root / "just-under").is_dir()
    assert not (root / ARCHIVE_DIR_NAME / "just-under").exists()


def test_retention_deletes_only_inside_archive(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    day = 86400.0
    archive_dir = root / ARCHIVE_DIR_NAME
    archive_dir.mkdir()
    _make_ws(archive_dir, "ancient", age_seconds=11 * day)
    _make_ws(archive_dir, "recent", age_seconds=9 * day)
    survivor = _make_ws(root, "active-ws")

    actions = plan_actions(
        scan(root), SweepLimits(retention_days=10.0, idle_archive_hours=10_000)
    )
    assert [a["action"] for a in actions] == ["DELETE_EXPIRED"]
    assert actions[0]["target"] == str(archive_dir / "ancient")

    results = apply_actions(actions, root, dry_run=False)
    assert results[0]["status"] == "deleted"
    assert not (archive_dir / "ancient").exists()
    assert (archive_dir / "recent").is_dir()

    crafted = [{"action": "DELETE_EXPIRED", "target": str(survivor)}]
    results = apply_actions(crafted, root, dry_run=False)
    assert results[0]["status"] == "refused"
    assert survivor.is_dir()


def test_count_overflow_orders_least_recent_first(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    hour = 3600.0
    ages = {"ws-10h": 10 * hour, "ws-8h": 8 * hour, "ws-6h": 6 * hour, "ws-2h": 2 * hour}
    for name, age in ages.items():
        _make_ws(root, name, age_seconds=age)

    limits = SweepLimits(idle_archive_hours=48.0, max_workspaces=2)
    actions = [a for a in plan_actions(scan(root), limits) if a["action"] == "ENFORCE_COUNT"]

    assert [Path(a["target"]).name for a in actions] == ["ws-10h", "ws-8h"]
    assert all("max_workspaces" in a["reason"] for a in actions)

    apply_actions(actions, root, dry_run=False)
    assert (root / "ws-6h").is_dir() and (root / "ws-2h").is_dir()
    assert (root / ARCHIVE_DIR_NAME / "ws-10h").is_dir()
    assert (root / ARCHIVE_DIR_NAME / "ws-8h").is_dir()


def test_root_size_enforcement_archives_largest_first(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    hour = 3600.0
    _make_ws(root, "idle-small", age_seconds=5 * hour, size_bytes=200)
    _make_ws(root, "big", size_bytes=5000)
    _make_ws(root, "mid", size_bytes=3000)

    limits = SweepLimits(
        idle_archive_hours=1.0,
        max_workspaces=100,
        root_max_gb=2500 / _BYTES_PER_GIB,
    )
    actions = plan_actions(scan(root), limits)

    by_action: dict[str, list[str]] = {}
    for item in actions:
        by_action.setdefault(item["action"], []).append(Path(item["target"]).name)
    # Idle archiving drains the idle population first; footprint enforcement
    # then trims the heaviest survivors until the active bytes fit.
    assert by_action["ARCHIVE_IDLE"] == ["idle-small"]
    assert by_action["ENFORCE_ROOT_SIZE"] == ["big", "mid"]

    apply_actions(actions, root, dry_run=False)
    remaining_active = sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir() and p.name != ARCHIVE_DIR_NAME
    )
    assert remaining_active == []


def test_dry_run_leaves_filesystem_untouched(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    day = 86400.0
    _make_ws(root, "stale", age_seconds=2 * day, size_bytes=16)
    archive_dir = root / ARCHIVE_DIR_NAME
    archive_dir.mkdir()
    _make_ws(archive_dir, "ancient", age_seconds=40 * day)
    marker = root / "stale" / "data.bin"
    before = _snapshot(root)
    marker_mtime = marker.stat().st_mtime

    report = run_sweep_once(
        root,
        SweepLimits(idle_archive_hours=24.0, retention_days=30.0, max_workspaces=100),
    )

    assert set(report) == {"inventory", "actions", "results"}
    assert len(report["results"]) == len(report["actions"])
    assert {r["status"] for r in report["results"]} <= {
        "would_archive",
        "would_delete",
    }
    assert any(a["action"] == "ARCHIVE_IDLE" for a in report["actions"])
    assert any(a["action"] == "DELETE_EXPIRED" for a in report["actions"])
    assert _snapshot(root) == before
    assert marker.stat().st_mtime == marker_mtime
    assert (root / "stale").is_dir()
    assert (archive_dir / "ancient").is_dir()


def test_dry_run_never_creates_archive_dir(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    _make_ws(root, "stale", age_seconds=48 * 3600)
    before = _snapshot(root)

    run_sweep_once(root, SweepLimits(idle_archive_hours=1.0))

    assert _snapshot(root) == before
    assert not (root / ARCHIVE_DIR_NAME).exists()


def test_symlink_escape_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("precious", encoding="utf-8")
    _set_tree_mtime(outside, time.time() - 10 * 3600)
    root = tmp_path / "root"
    root.mkdir()
    ghost = root / "ghost"
    ghost.symlink_to(outside, target_is_directory=True)

    inventory = scan(root)
    assert _entry(inventory, "ghost")["meta_ok"] is False

    actions = plan_actions(inventory, SweepLimits(idle_archive_hours=1.0))
    assert [a["action"] for a in actions] == ["ARCHIVE_IDLE"]

    results = apply_actions(actions, root, dry_run=False)
    assert all(r["status"] == "refused" for r in results)
    assert ghost.is_symlink()
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "precious"


def test_delete_via_symlink_outside_archive_refused(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "file.txt").write_text("data", encoding="utf-8")
    archive_dir = root / ARCHIVE_DIR_NAME
    archive_dir.mkdir()
    (archive_dir / "evil").symlink_to(victim, target_is_directory=True)

    results = apply_actions(
        [
            {
                "action": "DELETE_EXPIRED",
                "target": str(archive_dir / "evil"),
                "reason": "crafted escape attempt",
            }
        ],
        root,
        dry_run=False,
    )

    assert results[0]["status"] == "refused"
    assert victim.is_dir()
    assert (victim / "file.txt").exists()


def test_meta_ok_false_workspaces_reported_and_archived_without_crash(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    _make_ws(root, "broken-meta", age_seconds=72 * 3600, meta="corrupt")
    _make_ws(root, "no-meta", age_seconds=72 * 3600, meta=None)

    inventory = scan(root)
    assert all(e["meta_ok"] is False for e in inventory)

    report = run_sweep_once(
        root,
        SweepLimits(idle_archive_hours=24.0, max_workspaces=100),
        dry_run=False,
    )
    statuses = {r["status"] for r in report["results"]}
    assert statuses == {"archived"}
    leftovers = [p.name for p in root.iterdir() if p.is_dir() and p.name != ARCHIVE_DIR_NAME]
    assert leftovers == []
    assert (root / ARCHIVE_DIR_NAME / "broken-meta").is_dir()
    assert (root / ARCHIVE_DIR_NAME / "no-meta").is_dir()


def test_unknown_action_refused(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    target = _make_ws(root, "ws")

    results = apply_actions([{"action": "NUKE_FROM_ORBIT", "target": str(target)}], root)

    assert results[0]["status"] == "refused"
    assert target.is_dir()


def test_plan_actions_deduplicates_targets(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    hour = 3600.0
    _make_ws(root, "old-idle", age_seconds=96 * hour, size_bytes=9000)
    _make_ws(root, "fresh", size_bytes=9000)

    limits = SweepLimits(
        idle_archive_hours=1.0,
        max_workspaces=1,
        root_max_gb=1 / _BYTES_PER_GIB,
    )
    actions = plan_actions(scan(root), limits)

    targets = [a["target"] for a in actions]
    assert len(targets) == len(set(targets))
    # old-idle is claimed once by ARCHIVE_IDLE and never re-planned by the
    # count or footprint stages.
    assert targets.count(str(root / "old-idle")) == 1
