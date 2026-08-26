"""Workspace-per-chat core library.

Owns the on-disk layout ``<root>/<chat_id>/{journal.jsonl, STATE.md, notes/, meta.json}``,
a two-phase operation journal with torn-tail repair, and a derived STATE.md
cache. The journal is authoritative; STATE.md is always regenerable.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import app.config

# Verbatim chat-id contract: 6..64 chars, alphanumeric first character.
CHAT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{5,63}$")

WORKSPACE_SCHEMA = 1
JOURNAL_NAME = "journal.jsonl"
JOURNAL_ARCHIVE_NAME = "journal.jsonl.1"
STATE_NAME = "STATE.md"
META_NAME = "meta.json"
NOTES_NAME = "notes"

PAYLOAD_STRING_LIMIT_BYTES = 49152
PAYLOAD_EXCERPT_CHARS = 16384

_BIND_POLL_SECONDS = 0.01


class SquatError(RuntimeError):
    """A directory exists under the root without valid ownership metadata."""


class CapacityError(RuntimeError):
    """Configured workspace capacity prevents creating another workspace."""


class QuotaError(RuntimeError):
    """Per-workspace byte quota blocks the requested mutation."""

    def __init__(
        self,
        message: str,
        *,
        chat_id: str | None = None,
        used_bytes: int | None = None,
        quota_bytes: int | None = None,
    ) -> None:
        super().__init__(message)
        # Names mirror app.chat_errors._fields_from_exception so the E3
        # template renders concrete numbers instead of "?" placeholders.
        self.chat_id = chat_id
        self.used_bytes = used_bytes
        self.quota_bytes = quota_bytes


@dataclass(frozen=True)
class WorkspaceLimits:
    max_workspaces: int
    quota_mb: int
    root_max_gb: int
    journal_max_bytes: int
    idle_archive_hours: int
    retention_days: int
    resume_hint_minutes: int


@dataclass(frozen=True)
class BindResult:
    path: Path
    created: bool
    resumed_hint: str | None


def _int_limit(key: str, default: int) -> int:
    value = getattr(app.config, key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def read_limits() -> WorkspaceLimits:
    return WorkspaceLimits(
        max_workspaces=_int_limit("HOST_CHAT_MAX_WORKSPACES", 128),
        quota_mb=_int_limit("HOST_CHAT_QUOTA_MB", 2048),
        root_max_gb=_int_limit("HOST_CHAT_ROOT_MAX_GB", 24),
        journal_max_bytes=_int_limit("HOST_CHAT_JOURNAL_MAX_BYTES", 8_388_608),
        idle_archive_hours=_int_limit("HOST_CHAT_IDLE_ARCHIVE_HOURS", 72),
        retention_days=_int_limit("HOST_CHAT_RETENTION_DAYS", 30),
        resume_hint_minutes=_int_limit("HOST_CHAT_RESUME_HINT_MINUTES", 30),
    )


# ---------------------------------------------------------------------------
# Chat-id validation. The regex above is the verbatim floor. If a sibling
# validator exists (app.chat_identity may be built concurrently), it is reused
# only after proving agreement with that floor via probe strings; otherwise the
# local pattern decides alone.
# ---------------------------------------------------------------------------

_SIBLING_ATTRS = ("validate_chat_id", "is_valid_chat_id", "valid_chat_id")
_PROBE_VALID = ("abcdef", "x" * 64, "A9.z-k_m1", "abcde.f")
_PROBE_INVALID = ("", "abcde", "x" * 65, "_bcdef", "abcd e", ".bcdef")


def _agrees_with_verbatim_pattern(candidate: Callable[[Any], object]) -> bool:
    for probe in _PROBE_VALID:
        try:
            if not candidate(probe):
                return False
        except Exception:
            return False
    for probe in _PROBE_INVALID:
        try:
            if candidate(probe):
                return False
        except (TypeError, ValueError):
            continue
        except Exception:
            return False
    return True


def _sibling_validator() -> Callable[[Any], object] | None:
    try:
        # importlib (not `from app import ...`): the sibling may exist only in
        # sys.modules while the app package attribute is not yet bound.
        module = importlib.import_module("app.chat_identity")
    except Exception:
        return None
    candidate = None
    for name in _SIBLING_ATTRS:
        found = getattr(module, name, None)
        if callable(found):
            candidate = found
            break
    if candidate is not None and not _agrees_with_verbatim_pattern(candidate):
        return None
    return candidate


def is_valid_chat_id(chat_id: Any) -> bool:
    if not isinstance(chat_id, str) or CHAT_ID_PATTERN.fullmatch(chat_id) is None:
        return False
    sibling = _sibling_validator()
    if sibling is None:
        return True
    try:
        return bool(sibling(chat_id))
    except ValueError:
        return False
    except Exception:
        return True


def validate_chat_id(chat_id: Any) -> str:
    if not is_valid_chat_id(chat_id):
        raise ValueError(
            "chat_id must match ^[A-Za-z0-9][A-Za-z0-9._-]{5,63}$ "
            "(length 6..64, first character alphanumeric)."
        )
    return chat_id


# ---------------------------------------------------------------------------
# Payload hygiene: degrade-by-excerpt so records are never dropped.
# ---------------------------------------------------------------------------


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, str):
        raw = value.encode("utf-8", errors="replace")
        if len(raw) <= PAYLOAD_STRING_LIMIT_BYTES:
            return value
        excerpt = value[:PAYLOAD_EXCERPT_CHARS]
        kept = excerpt.encode("utf-8", errors="replace")
        dropped = len(raw) - len(kept)
        return f"{excerpt}...<truncated {dropped} bytes>"
    if isinstance(value, dict):
        return {key: sanitize_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_payload(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# Journal primitives.
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_line_bytes(obj: Mapping[str, Any]) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(tmp, path)


def load_workspace_meta(ws_dir: Path, expected_chat_id: str | None = None) -> dict[str, Any]:
    meta_path = ws_dir / META_NAME
    try:
        raw = meta_path.read_bytes()
    except OSError as exc:
        raise SquatError(f"workspace metadata missing: {ws_dir.name}") from exc
    try:
        meta = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SquatError(f"workspace metadata unreadable: {ws_dir.name}") from exc
    next_seq = meta.get("next_seq") if isinstance(meta, dict) else None
    if (
        not isinstance(meta, dict)
        or meta.get("schema") != WORKSPACE_SCHEMA
        or not isinstance(meta.get("chat_id"), str)
        or not isinstance(next_seq, int)
        or isinstance(next_seq, bool)
    ):
        raise SquatError(f"workspace metadata invalid: {ws_dir.name}")
    if expected_chat_id is not None and meta["chat_id"] != expected_chat_id:
        raise SquatError(f"workspace owned by another chat id: {ws_dir.name}")
    return meta


def _repair_torn_tail(journal: Path) -> int:
    """Drop only an incomplete trailing line; complete lines are never touched."""
    try:
        size = journal.stat().st_size
    except OSError:
        return 0
    if size == 0:
        return 0
    with journal.open("rb") as handle:
        handle.seek(size - 1)
        if handle.read(1) == b"\n":
            return 0
        handle.seek(0)
        data = handle.read()
    keep = data.rfind(b"\n") + 1
    if keep == size:
        return 0
    os.truncate(journal, keep)
    return size - keep


def read_journal_records(ws_dir: Path) -> list[dict[str, Any]]:
    """Merged oldest-first events from the rotation archive plus active journal."""
    records: list[dict[str, Any]] = []
    for name in (JOURNAL_ARCHIVE_NAME, JOURNAL_NAME):
        try:
            raw = (ws_dir / name).read_bytes()
        except OSError:
            continue
        for line in raw.splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(item, dict):
                records.append(item)
    return records


def pending_operations(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    started: dict[str, dict[str, Any]] = {}
    for event in events:
        op = event.get("op")
        event_type = event.get("type")
        if not isinstance(op, str):
            continue
        if event_type == "op_started":
            started[op] = dict(event)
        elif event_type == "op_result":
            started.pop(op, None)
    return list(started.values())


def last_activity(ws_dir: Path) -> datetime | None:
    candidates: list[datetime] = []
    for event in read_journal_records(ws_dir):
        stamp = event.get("ts")
        if not isinstance(stamp, str):
            continue
        try:
            moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        candidates.append(moment)
    for name in (JOURNAL_NAME, META_NAME):
        try:
            mtime = (ws_dir / name).stat().st_mtime
        except OSError:
            continue
        candidates.append(datetime.fromtimestamp(mtime, tz=timezone.utc))
    return max(candidates) if candidates else None


# ---------------------------------------------------------------------------
# STATE.md rendering (pure, byte-deterministic).
# ---------------------------------------------------------------------------


def render_state_md(meta: Mapping[str, Any], events: Iterable[Mapping[str, Any]]) -> str:
    event_list = [dict(event) for event in events]
    event_list.sort(key=lambda item: item["seq"] if isinstance(item.get("seq"), int) else float("inf"))

    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = ["# Workspace State", ""]
    for key in sorted(meta, key=str):
        shown = meta[key] if isinstance(meta[key], str) else json.dumps(
            meta[key], sort_keys=True, separators=(",", ":")
        )
        lines.append(f"- {cell(key)}: {cell(shown)}")

    lines.extend(["", "## Pending Operations", ""])
    pending = pending_operations(event_list)
    if not pending:
        lines.append("(none)")
    for item in pending:
        lines.append(
            "- seq={seq} op={op} kind={kind} started={ts}".format(
                seq=cell(item.get("seq", "?")),
                op=cell(item.get("op", "?")),
                kind=cell(item.get("kind", "?")),
                ts=cell(item.get("ts", "?")),
            )
        )

    lines.extend(
        [
            "",
            "## Events",
            "",
            "| seq | ts | type | op | kind | ok |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in event_list:
        ok_value = item.get("ok")
        ok_cell = "" if ok_value is None else cell(bool(ok_value)).lower()
        lines.append(
            "| {seq} | {ts} | {etype} | {op} | {kind} | {okc} |".format(
                seq=cell(item.get("seq", "?")),
                ts=cell(item.get("ts", "?")),
                etype=cell(item.get("type", "?")),
                op=cell(item.get("op", "?")),
                kind=cell(item.get("kind", "?")),
                okc=ok_cell,
            )
        )
    return "\n".join(lines) + "\n"


def rebuild_state(ws_dir: Path) -> str:
    """Regenerate STATE.md purely from meta + journal; never trusts the cache."""
    meta = load_workspace_meta(ws_dir)
    text = render_state_md(meta, read_journal_records(ws_dir))
    _atomic_write(ws_dir / STATE_NAME, text.encode("utf-8"))
    return text


# ---------------------------------------------------------------------------
# Quota accounting. Walked only on mutation points (create/bind, appends);
# read APIs never pay for it, so no cache is needed.
# ---------------------------------------------------------------------------


def _workspace_bytes(ws: Path) -> int:
    total = 0
    stack = [ws]
    while stack:
        try:
            entries = list(stack.pop().iterdir())
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    total += entry.lstat().st_size
                elif entry.is_dir():
                    stack.append(entry)
                else:
                    total += entry.stat().st_size
            except OSError:
                continue
    return total


# ---------------------------------------------------------------------------
# Manager.
# ---------------------------------------------------------------------------


class WorkspaceManager:
    def __init__(self, root: Path, *, bind_wait_seconds: float = 5.0) -> None:
        self.root = Path(root)
        # A losing racer waits here for the winner's meta.json to appear;
        # past the deadline an existing directory counts as a squat.
        self.bind_wait_seconds = float(bind_wait_seconds)
        self._master_lock = threading.Lock()
        self._workspace_locks: dict[str, threading.Lock] = {}

    def limits(self) -> WorkspaceLimits:
        return read_limits()

    def workspace_path(self, chat_id: str) -> Path:
        return self.root / validate_chat_id(chat_id)

    def _lock_for(self, chat_id: str) -> threading.Lock:
        with self._master_lock:
            lock = self._workspace_locks.get(chat_id)
            if lock is None:
                lock = threading.Lock()
                self._workspace_locks[chat_id] = lock
            return lock

    def create_or_bind(self, chat_id: str) -> BindResult:
        validated = validate_chat_id(chat_id)
        self.root.mkdir(parents=True, exist_ok=True)
        with self._lock_for(validated):
            ws = self.root / validated
            if not ws.exists():
                self._enforce_capacity()
            try:
                os.mkdir(ws)
            except FileExistsError:
                return self._bind_existing(validated, ws)
            return self._initialize(validated, ws)

    def _enforce_capacity(self) -> None:
        max_workspaces = read_limits().max_workspaces
        if max_workspaces <= 0:
            return
        try:
            count = sum(1 for entry in self.root.iterdir() if entry.is_dir())
        except OSError:
            return
        if count >= max_workspaces:
            raise CapacityError(
                f"max_workspaces={max_workspaces} reached under {self.root}"
            )

    def _enforce_quota(
        self, ws: Path, chat_id: str, incoming_bytes: int | None = None
    ) -> None:
        quota_mb = read_limits().quota_mb
        if quota_mb <= 0:
            return
        quota_bytes = quota_mb * 1024 * 1024
        used = _workspace_bytes(ws)
        if used < quota_bytes:
            return
        # An append is refused only when its payload would grow the footprint;
        # bind-time enforcement has no incoming bytes and refuses outright.
        if incoming_bytes is not None and incoming_bytes <= 0:
            return
        detail = "" if incoming_bytes is None else f"; refusing {incoming_bytes} more"
        raise QuotaError(
            f"chat {chat_id} workspace over quota: "
            f"{used} of {quota_bytes} bytes used{detail}",
            chat_id=chat_id,
            used_bytes=used,
            quota_bytes=quota_bytes,
        )

    def _initialize(self, chat_id: str, ws: Path) -> BindResult:
        (ws / NOTES_NAME).mkdir(exist_ok=True)
        meta = {
            "chat_id": chat_id,
            "created_at": _utc_now_iso(),
            "schema": WORKSPACE_SCHEMA,
            "next_seq": 1,
        }
        meta_path = ws / META_NAME
        try:
            descriptor = os.open(meta_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise SquatError(f"workspace metadata already present: {ws.name}") from exc
        try:
            os.write(descriptor, _json_line_bytes(meta))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        (ws / JOURNAL_NAME).touch(mode=0o600)
        rebuild_state(ws)
        return BindResult(path=ws, created=True, resumed_hint=None)

    def _bind_existing(self, chat_id: str, ws: Path) -> BindResult:
        deadline = time.monotonic() + self.bind_wait_seconds
        while True:
            if (ws / META_NAME).exists():
                load_workspace_meta(ws, expected_chat_id=chat_id)
                # Ownership first (squat defense), then quota, before any write.
                self._enforce_quota(ws, chat_id)
                return BindResult(path=ws, created=False, resumed_hint=self._resume_hint(ws))
            if time.monotonic() >= deadline:
                raise SquatError(f"directory exists without workspace metadata: {ws.name}")
            time.sleep(_BIND_POLL_SECONDS)

    def _resume_hint(self, ws: Path) -> str | None:
        minutes = read_limits().resume_hint_minutes
        if minutes <= 0:
            return None
        moment = last_activity(ws)
        if moment is None:
            return None
        age_seconds = (datetime.now(timezone.utc) - moment).total_seconds()
        if age_seconds <= minutes * 60:
            return f"resuming: activity {int(age_seconds // 60)} minute(s) ago"
        return None

    def append_op_started(
        self,
        chat_id: str,
        op_id: str,
        kind: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        base = {
            "type": "op_started",
            "op": str(op_id),
            "kind": str(kind),
            "payload": sanitize_payload({} if payload is None else payload),
        }
        return self._append_op(chat_id, base, rotates=True)

    def append_op_result(
        self,
        chat_id: str,
        op_id: str,
        ok: bool,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        base = {
            "type": "op_result",
            "op": str(op_id),
            "ok": bool(ok),
            "payload": sanitize_payload({} if payload is None else payload),
        }
        return self._append_op(chat_id, base, rotates=False)

    def _append_op(self, chat_id: str, base: dict[str, Any], *, rotates: bool) -> dict[str, Any]:
        validated = validate_chat_id(chat_id)
        with self._lock_for(validated):
            ws = self.root / validated
            meta = load_workspace_meta(ws, expected_chat_id=validated)
            journal = ws / JOURNAL_NAME
            _repair_torn_tail(journal)
            record = {"seq": int(meta["next_seq"]), "ts": _utc_now_iso(), **base}
            encoded = _json_line_bytes(record)
            # Gate before rotation: rotation only relocates bytes, the append
            # is what would grow the footprint past the quota.
            self._enforce_quota(ws, validated, len(encoded))
            if rotates and self._needs_rotation(journal, len(encoded)):
                os.replace(journal, ws / JOURNAL_ARCHIVE_NAME)
            descriptor = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(descriptor, encoded)
            finally:
                os.close(descriptor)
            meta["next_seq"] = int(meta["next_seq"]) + 1
            _atomic_write(ws / META_NAME, _json_line_bytes(meta))
            return record

    def _needs_rotation(self, journal: Path, incoming_bytes: int) -> bool:
        limit = read_limits().journal_max_bytes
        if limit <= 0:
            return False
        try:
            size = journal.stat().st_size
        except OSError:
            size = 0
        return size + incoming_bytes > limit

    def read_events(self, chat_id: str) -> list[dict[str, Any]]:
        validated = validate_chat_id(chat_id)
        with self._lock_for(validated):
            ws = self.root / validated
            load_workspace_meta(ws, expected_chat_id=validated)
            _repair_torn_tail(ws / JOURNAL_NAME)
            return read_journal_records(ws)

    def pending_ops(self, chat_id: str) -> list[dict[str, Any]]:
        return pending_operations(self.read_events(chat_id))

    def rebuild_state(self, chat_id: str) -> str:
        validated = validate_chat_id(chat_id)
        with self._lock_for(validated):
            return rebuild_state(self.root / validated)
