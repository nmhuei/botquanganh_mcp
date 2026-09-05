"""Tests for the ``python -m app.chat_sweeper`` entrypoint and its gating logic."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

from app import chat_sweeper
from app.chat_sweeper import ARCHIVE_DIR_NAME, META_FILENAME, SweepLimits, decide_sweep

REPO_ROOT = Path(__file__).resolve().parents[1]

_DAY = 86400.0


def _fake_config(**overrides):
    base = {
        "HOST_CHAT_WORKSPACES": True,
        "HOST_CHAT_ROOT": "",
        "HOST_CHAT_IDLE_ARCHIVE_HOURS": 24,
        "HOST_CHAT_RETENTION_DAYS": 30,
        "HOST_CHAT_MAX_WORKSPACES": 64,
        "HOST_CHAT_ROOT_MAX_GB": 100.0,
    }
    base.update(overrides)
    return types.SimpleNamespace(**base)


def _make_ws(
    root: Path, name: str, *, age_seconds: float = 0.0, meta: str | None = "good"
) -> Path:
    ws = root / name
    ws.mkdir(parents=True)
    if meta == "good":
        (ws / META_FILENAME).write_text(json.dumps({"chat_id": name}), encoding="utf-8")
    if age_seconds:
        for path in (ws, *ws.rglob("*")):
            os.utime(path, (time.time() - age_seconds,) * 2)
    return ws


def _payloads(out: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]


def test_dry_run_prints_action_lines_and_summary(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    stale = _make_ws(root, "stale", age_seconds=3 * _DAY)
    archive_dir = root / ARCHIVE_DIR_NAME
    archive_dir.mkdir()
    ancient = _make_ws(archive_dir, "ancient", age_seconds=40 * _DAY)
    before = sorted(str(p.relative_to(root)) for p in root.rglob("*"))

    out = io.StringIO()
    rc = chat_sweeper._main([], config=_fake_config(HOST_CHAT_ROOT=str(root)), stdout=out)

    assert rc == 0
    payloads = _payloads(out)
    summary = payloads[-1]["summary"]
    action_lines = payloads[:-1]
    assert {item["action"] for item in action_lines} == {
        "ARCHIVE_IDLE",
        "DELETE_EXPIRED",
    }
    assert all(item["status"].startswith("would_") for item in action_lines)
    assert all(item["reason"] for item in action_lines)
    assert summary["dry_run"] is True
    assert summary["scanned"] == 2
    assert summary["planned"] == len(action_lines)
    assert summary["errors"] == 0
    # Dry run must not touch the filesystem.
    assert sorted(str(p.relative_to(root)) for p in root.rglob("*")) == before
    assert stale.is_dir() and ancient.is_dir()


def test_apply_performs_moves_and_deletes(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    _make_ws(root, "stale", age_seconds=3 * _DAY)
    archive_dir = root / ARCHIVE_DIR_NAME
    archive_dir.mkdir()
    _make_ws(archive_dir, "ancient", age_seconds=40 * _DAY)

    out = io.StringIO()
    rc = chat_sweeper._main(
        ["--apply"], config=_fake_config(HOST_CHAT_ROOT=str(root)), stdout=out
    )

    assert rc == 0
    summary = _payloads(out)[-1]["summary"]
    assert summary["dry_run"] is False
    assert summary["status_counts"]["archived"] == 1
    assert summary["status_counts"]["deleted"] == 1
    assert not (root / "stale").exists()
    assert (root / ARCHIVE_DIR_NAME / "stale").is_dir()
    assert not (archive_dir / "ancient").exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores chmod 000")
def test_unreadable_expired_target_counted_not_fatal(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    healthy = _make_ws(root, "stale", age_seconds=3 * _DAY)
    archive_dir = root / ARCHIVE_DIR_NAME
    archive_dir.mkdir()
    locked = _make_ws(archive_dir, "locked", age_seconds=40 * _DAY)
    os.chmod(locked, 0o000)

    out = io.StringIO()
    try:
        rc = chat_sweeper._main(
            ["--apply"], config=_fake_config(HOST_CHAT_ROOT=str(root)), stdout=out
        )
    finally:
        os.chmod(locked, 0o755)

    assert rc == 0
    payloads = _payloads(out)
    summary = payloads[-1]["summary"]
    by_action = {item["action"]: item for item in payloads[:-1]}
    # The unreadable target fails individually; the sweep still finishes.
    assert summary["errors"] >= 1
    assert by_action["DELETE_EXPIRED"]["status"] == "error"
    assert locked.is_dir()
    # The healthy sibling is unaffected.
    assert by_action["ARCHIVE_IDLE"]["status"] == "archived"
    assert not healthy.exists()
    assert (root / ARCHIVE_DIR_NAME / "stale").is_dir()


def test_json_mode_emits_single_document(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    _make_ws(root, "stale", age_seconds=3 * _DAY)

    out = io.StringIO()
    rc = chat_sweeper._main(
        ["--json"], config=_fake_config(HOST_CHAT_ROOT=str(root)), stdout=out
    )

    assert rc == 0
    document = json.loads(out.getvalue())  # exactly one parseable document
    assert set(document) >= {
        "root",
        "dry_run",
        "inventory",
        "actions",
        "results",
        "summary",
    }
    assert document["dry_run"] is True
    assert document["summary"]["planned"] == len(document["actions"])


def test_root_flag_overrides_config_root(tmp_path):
    configured_root = tmp_path / "configured"
    configured_root.mkdir()
    actual_root = tmp_path / "actual"
    actual_root.mkdir()
    _make_ws(actual_root, "ws", age_seconds=3 * _DAY)

    out = io.StringIO()
    rc = chat_sweeper._main(
        ["--root", str(actual_root)],
        config=_fake_config(HOST_CHAT_ROOT=str(configured_root)),
        stdout=out,
    )

    assert rc == 0
    payloads = _payloads(out)
    assert payloads[-1]["summary"]["scanned"] == 1
    assert payloads[0]["target"] == str(actual_root / "ws")


def test_limits_from_config_maps_attributes_with_defaults():
    limits = chat_sweeper._limits_from_config(
        _fake_config(
            HOST_CHAT_IDLE_ARCHIVE_HOURS=5,
            HOST_CHAT_RETENTION_DAYS=7,
            HOST_CHAT_MAX_WORKSPACES=9,
            HOST_CHAT_ROOT_MAX_GB=1.5,
        )
    )
    assert (
        limits.idle_archive_hours,
        limits.retention_days,
        limits.max_workspaces,
        limits.root_max_gb,
    ) == (5.0, 7.0, 9, 1.5)

    bare = chat_sweeper._limits_from_config(types.SimpleNamespace())
    assert bare == SweepLimits()


def test_decide_sweep_gating():
    now = 1_000_000.0

    # Disabled master switch wins over everything.
    assert decide_sweep(
        enabled=False, now_ts=now, last_sweep_ts=0, interval_minutes=60
    ) == {"run": False, "apply": False, "reason": "chat workspaces disabled"}

    # Interval not yet elapsed: no run even with apply requested.
    assert decide_sweep(
        enabled=True, now_ts=now, last_sweep_ts=now - 3599, interval_minutes=60
    )["run"] is False

    due = decide_sweep(enabled=True, now_ts=now, last_sweep_ts=now - 3600, interval_minutes=60)
    assert due == {"run": True, "apply": False, "reason": "interval elapsed"}

    applied = decide_sweep(
        enabled=True,
        now_ts=now,
        last_sweep_ts=now - 3601,
        interval_minutes=60,
        apply_requested=True,
    )
    assert applied["run"] is True and applied["apply"] is True

    # Non-positive or garbage intervals disable periodic sweeping.
    for bad_interval in (0, -5, "soon"):
        decision = decide_sweep(
            enabled=True, now_ts=now, last_sweep_ts=0, interval_minutes=bad_interval
        )
        assert decision["run"] is False and decision["apply"] is False


def test_python_dash_m_smoke_dry_run_default(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    _make_ws(root, "stale", age_seconds=3 * _DAY)
    env = dict(os.environ)
    env.update(
        {
            "HOST_CHAT_IDLE_ARCHIVE_HOURS": "1",
            "HOST_CHAT_RETENTION_DAYS": "30",
            "HOST_CHAT_MAX_WORKSPACES": "64",
            "HOST_CHAT_ROOT_MAX_GB": "100",
        }
    )

    proc = subprocess.run(
        [sys.executable, "-m", "app.chat_sweeper", "--root", str(root)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        timeout=120,
    )

    assert proc.returncode == 0, proc.stderr
    payloads = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    assert payloads[-1]["summary"]["scanned"] == 1
    assert any(item.get("action") == "ARCHIVE_IDLE" for item in payloads[:-1])
    # Default mode is a dry run: the workspace survives untouched.
    assert (root / "stale").is_dir()
