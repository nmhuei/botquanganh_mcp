"""Lifecycle sweeping for chat workspaces, expressed as pure logic.

No daemon thread lives here: callers invoke :func:`run_sweep_once` whenever a
sweep is due. Every stage is side-effect free until :func:`apply_actions`, and
even that stage refuses any target whose resolved path escapes the workspace
root (deletes are further restricted to paths strictly inside
``<root>/.archive``).
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ARCHIVE_DIR_NAME = ".archive"
META_FILENAME = "meta.json"

_ACTION_ARCHIVE = frozenset({"ARCHIVE_IDLE", "ENFORCE_COUNT", "ENFORCE_ROOT_SIZE"})
_ACTION_DELETE = "DELETE_EXPIRED"

_SECONDS_PER_HOUR = 3600
_SECONDS_PER_DAY = 86400
_BYTES_PER_GIB = 1024**3


@dataclass(frozen=True)
class SweepLimits:
    """Thresholds driving :func:`plan_actions`.

    Callers normally build this from config via getattr(config, "...", default)
    so the module keeps working whether or not the env keys exist yet.
    """

    idle_archive_hours: float = 24.0 * 7
    retention_days: float = 30.0
    max_workspaces: int = 64
    root_max_gb: float = 10.0


def _tree_stats(directory: Path) -> tuple[int, float]:
    """Return (total regular-file bytes, newest mtime seen) without following symlinks.

    An unreadable subtree degrades to whatever was gathered before the error;
    the directory's own mtime seeds the activity timestamp so an empty or
    unreadable workspace still reports something sane instead of crashing.
    """
    total = 0
    newest = 0.0
    try:
        newest = directory.stat().st_mtime
    except OSError:
        return total, newest
    stack = [directory]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    newest = max(newest, entry.stat(follow_symlinks=False).st_mtime)
                    stack.append(Path(entry.path))
                else:
                    stat = entry.stat(follow_symlinks=False)
                    total += stat.st_size
                    newest = max(newest, stat.st_mtime)
            except OSError:
                continue
    return total, newest


def _meta_ok(directory: Path) -> bool:
    try:
        parsed = json.loads((directory / META_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(parsed, dict)


def scan(root: Path) -> list[dict[str, Any]]:
    """Inventory every workspace directory under ``root``.

    Active workspaces get full stats; entries inside ``<root>/.archive`` are
    summarized only (no size walk) because their bytes are already cold and
    retention only needs the activity timestamp.
    """
    root = Path(root)
    inventory: list[dict[str, Any]] = []
    if not root.is_dir():
        return inventory
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        try:
            if not child.is_dir():
                continue
        except OSError:
            continue
        if child.name == ARCHIVE_DIR_NAME:
            for archived in sorted(child.iterdir(), key=lambda item: item.name):
                try:
                    if not archived.is_dir():
                        continue
                except OSError:
                    continue
                _, mtime = _tree_stats(archived)
                inventory.append(
                    {
                        "path": str(archived),
                        "chat_id": archived.name,
                        "meta_ok": _meta_ok(archived),
                        "size_bytes": None,
                        "mtime": mtime,
                        "archived": True,
                    }
                )
            continue
        size_bytes, mtime = _tree_stats(child)
        inventory.append(
            {
                "path": str(child),
                "chat_id": child.name,
                "meta_ok": _meta_ok(child),
                "size_bytes": size_bytes,
                "mtime": mtime,
                "archived": False,
            }
        )
    return inventory


def plan_actions(
    inventory: list[dict[str, Any]], limits: SweepLimits
) -> list[dict[str, Any]]:
    """Map an inventory onto an ordered, side-effect-free action list.

    Execution order matches emission order: expired archived workspaces are
    deleted first, then idle workspaces are archived (oldest activity first),
    then count and finally footprint enforcement top up whatever the earlier
    stages left behind. Each target appears at most once, keeping the first
    action planned for it. Archiving moves bytes within ``root``, so
    ``root_max_gb`` is enforced against the active footprint only; shrinking
    the archive is ``DELETE_EXPIRED``'s job.
    """
    now = time.time()
    actions: list[dict[str, Any]] = []
    planned: set[str] = set()

    def plan(action: str, entry: dict[str, Any], reason: str) -> None:
        target = str(entry["path"])
        if target in planned:
            return
        planned.add(target)
        actions.append({"action": action, "target": target, "reason": reason})

    def age(entry: dict[str, Any]) -> float:
        return now - float(entry.get("mtime") or 0.0)

    archived_entries = [e for e in inventory if e.get("archived")]
    active = [e for e in inventory if not e.get("archived")]

    expired = [
        e
        for e in archived_entries
        if age(e) > limits.retention_days * _SECONDS_PER_DAY
    ]
    expired.sort(key=lambda e: (float(e.get("mtime") or 0.0), e["chat_id"]))
    for entry in expired:
        plan(
            _ACTION_DELETE,
            entry,
            "archived {:.1f}d ago exceeds retention_days={:g}".format(
                age(entry) / _SECONDS_PER_DAY, limits.retention_days
            ),
        )

    idle = [
        e
        for e in active
        if age(e) > limits.idle_archive_hours * _SECONDS_PER_HOUR
    ]
    idle.sort(key=lambda e: (float(e.get("mtime") or 0.0), e["chat_id"]))
    for entry in idle:
        plan(
            "ARCHIVE_IDLE",
            entry,
            "idle {:.1f}h exceeds idle_archive_hours={:g}".format(
                age(entry) / _SECONDS_PER_HOUR, limits.idle_archive_hours
            ),
        )

    remaining = [e for e in active if str(e["path"]) not in planned]

    overflow = len(remaining) - limits.max_workspaces
    if overflow > 0:
        surplus = sorted(remaining, key=lambda e: (float(e.get("mtime") or 0.0), e["chat_id"]))
        count_reason = (
            "{:d} active workspaces exceed max_workspaces={:d}".format(
                len(remaining), limits.max_workspaces
            )
        )
        for entry in surplus[:overflow]:
            plan("ENFORCE_COUNT", entry, count_reason)
        remaining = [e for e in remaining if str(e["path"]) not in planned]

    max_bytes = limits.root_max_gb * _BYTES_PER_GIB
    footprint = sum(int(e.get("size_bytes") or 0) for e in remaining)
    if footprint > max_bytes:
        heaviest = sorted(
            remaining,
            key=lambda e: (-int(e.get("size_bytes") or 0), float(e.get("mtime") or 0.0)),
        )
        for entry in heaviest:
            if footprint <= max_bytes:
                break
            plan(
                "ENFORCE_ROOT_SIZE",
                entry,
                "active footprint {:.2f}GiB exceeds root_max_gb={:g}".format(
                    footprint / _BYTES_PER_GIB, limits.root_max_gb
                ),
            )
            footprint -= int(entry.get("size_bytes") or 0)

    return actions


def _is_within(path: Path, boundary: Path) -> bool:
    try:
        path.relative_to(boundary)
    except ValueError:
        return False
    return True


def _refused(result: dict[str, Any], detail: str) -> dict[str, Any]:
    return {**result, "status": "refused", "detail": detail}


def _apply_one(
    kind: Any, target: Any, root: Path, archive_root: Path, dry_run: bool
) -> dict[str, Any]:
    result: dict[str, Any] = {"action": str(kind), "target": str(target)}
    try:
        resolved = Path(target).resolve()
    except OSError:
        return _refused(result, "path cannot be resolved")
    if resolved == root or not _is_within(resolved, root):
        return _refused(result, "resolved path escapes the workspace root")

    if kind in _ACTION_ARCHIVE:
        if resolved == archive_root or _is_within(resolved, archive_root):
            return _refused(result, "target already lives inside the archive")
        try:
            if not resolved.is_dir():
                return {**result, "status": "skipped", "detail": "target is missing"}
        except OSError as exc:
            return {**result, "status": "error", "detail": str(exc)}
        destination = archive_root / resolved.name
        try:
            exists = destination.exists()
        except OSError as exc:
            return {**result, "status": "error", "detail": str(exc)}
        if exists:
            return _refused(result, "archive destination already exists")
        if dry_run:
            return {**result, "status": "would_archive", "destination": str(destination)}
        try:
            archive_root.mkdir(parents=True, exist_ok=True)
            shutil.move(str(resolved), str(destination))
        except OSError as exc:
            return {**result, "status": "error", "detail": str(exc)}
        return {**result, "status": "archived", "destination": str(destination)}

    if kind == _ACTION_DELETE:
        # Deletes are only ever legal strictly inside <root>/.archive; the
        # resolved-path comparison is what defeats symlink escapes.
        if resolved == archive_root or not _is_within(resolved, archive_root):
            return _refused(result, "deletes are restricted to <root>/.archive")
        try:
            if not resolved.exists() and not resolved.is_symlink():
                return {**result, "status": "skipped", "detail": "target is missing"}
        except OSError as exc:
            return {**result, "status": "error", "detail": str(exc)}
        if dry_run:
            return {**result, "status": "would_delete"}
        try:
            if resolved.is_dir() and not resolved.is_symlink():
                shutil.rmtree(resolved)
            else:
                resolved.unlink()
        except OSError as exc:
            return {**result, "status": "error", "detail": str(exc)}
        return {**result, "status": "deleted"}

    return _refused(result, "unknown action")


def apply_actions(
    actions: list[dict[str, Any]], root: Path, dry_run: bool = True
) -> list[dict[str, Any]]:
    """Execute (or simulate) an ordered action list against ``root``.

    Returns one result dict per action with a ``status`` of ``archived``,
    ``deleted``, ``would_archive``, ``would_delete``, ``skipped``, ``refused``
    or ``error``. ``dry_run=True`` performs no filesystem mutation whatsoever,
    including not creating ``<root>/.archive``.
    """
    resolved_root = Path(root).resolve()
    archive_root = resolved_root / ARCHIVE_DIR_NAME
    return [
        _apply_one(item.get("action"), item.get("target"), resolved_root, archive_root, dry_run)
        for item in actions
    ]


def run_sweep_once(
    root: Path, limits: SweepLimits, dry_run: bool = True
) -> dict[str, Any]:
    """Compose scan -> plan -> apply into a single sweep report."""
    inventory = scan(root)
    actions = plan_actions(inventory, limits)
    results = apply_actions(actions, root, dry_run=dry_run)
    return {"inventory": inventory, "actions": actions, "results": results}
