"""Workspace-per-chat core library.

Owns the on-disk layout ``<root>/<chat_id>/{journal.jsonl, STATE.md, notes/, meta.json}``,
a two-phase operation journal with torn-tail repair, and a derived STATE.md
cache. The journal is authoritative; STATE.md is always regenerable.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import os
import re
import secrets
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
JOURNAL_SCHEMA_VERSION = 2
JOURNAL_DATASET = "bqa.workspace"
JOURNAL_SOURCE = "workspace_journal"

# OpenTelemetry-compatible severity numbers for the subset emitted by the
# workspace journal. The journal keeps the human-readable text too so the CLI
# never needs to reverse-map numbers just to display a row.
_SEVERITY_NUMBERS = {"DEBUG": 5, "INFO": 9, "WARN": 13, "ERROR": 17}
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(?:^|[_-])(authorization|cookie|password|passwd|secret|session(?:[_-]?id)?|token|api[_-]?key)(?:$|[_-])"
)
_BEARER_RE = re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/=-]+")
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b([A-Za-z0-9_]*(?:api[_-]?key|authorization|password|passwd|secret|session[_-]?id|token)[A-Za-z0-9_]*\s*=\s*)([^\s'\"]+)"
)
_SECRET_FLAG_RE = re.compile(
    r"(?i)(--(?:api-key|authorization|password|passwd|secret|session-id|token)(?:=|\s+))([^\s'\"]+)"
)

_BIND_POLL_SECONDS = 0.01


class SquatError(RuntimeError):
    """A directory exists under the root without valid ownership metadata."""


class CapacityError(RuntimeError):
    """Configured workspace capacity prevents creating another workspace."""


class ResumeUnauthorizedError(RuntimeError):
    """Resume token was invalid or missing for an existing workspace."""

    def __init__(self, message: str, *, chat_id: str | None = None) -> None:
        super().__init__(message)
        self.chat_id = chat_id


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


def generate_chat_id(label: str | None = None) -> str:
    """Generate a server-assigned unique chat_id.

    Format: cw-YYYYMMDD-[sanitized_label-]8hex
    """
    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    rand_part = secrets.token_hex(4)  # 8 hex chars
    if label:
        clean_label = re.sub(r"[^A-Za-z0-9_-]", "-", str(label).strip()).strip("-_")
        max_label_len = 64 - 22  # "cw-YYYYMMDD-" (12) + "-" (1) + 8hex (8) + 1 = 22
        clean_label = clean_label[:max_label_len].rstrip("-_")
        if clean_label:
            candidate = f"cw-{date_part}-{clean_label}-{rand_part}"
            if CHAT_ID_PATTERN.fullmatch(candidate):
                return candidate
    return f"cw-{date_part}-{rand_part}"


def generate_session_token() -> tuple[str, str]:
    """Generate a raw 32-byte hex secret and its SHA-256 hash.

    Returns (raw_token, token_hash).
    """
    raw_token = secrets.token_hex(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    return raw_token, token_hash


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest of a token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_session_token(token: str, token_hash: str) -> bool:
    """Constant-time comparison between hashed token and expected token_hash."""
    if not token or not token_hash:
        return False
    candidate_hash = hash_token(token)
    return hmac.compare_digest(candidate_hash.encode("ascii"), token_hash.encode("ascii"))


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
    chat_id: str = ""
    session_token: str | None = None


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


def _redact_sensitive_text(value: str) -> str:
    redacted = _BEARER_RE.sub(r"\1<redacted>", value)
    redacted = _SECRET_ASSIGN_RE.sub(r"\1<redacted>", redacted)
    return _SECRET_FLAG_RE.sub(r"\1<redacted>", redacted)


def sanitize_payload(value: Any) -> Any:
    """Redact obvious secrets and cap large strings before display/storage.

    Key-based redaction is deliberately conservative and recursive. String
    redaction handles common bearer/assignment/CLI-flag forms so command and
    query metadata cannot trivially leak credentials into the workspace log.
    """
    if isinstance(value, str):
        value = _redact_sensitive_text(value)
        raw = value.encode("utf-8", errors="replace")
        if len(raw) <= PAYLOAD_STRING_LIMIT_BYTES:
            return value
        excerpt = value[:PAYLOAD_EXCERPT_CHARS]
        kept = excerpt.encode("utf-8", errors="replace")
        dropped = len(raw) - len(kept)
        return f"{excerpt}...<truncated {dropped} bytes>"
    if isinstance(value, dict):
        clean: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and _SENSITIVE_KEY_RE.search(key):
                clean[key] = "<redacted>"
            elif isinstance(key, str) and key.lower() == "command" and isinstance(item, str):
                # Match the executor/audit posture: commands may contain
                # positional secrets that no redaction regex can reliably
                # identify. Preserve the key for backwards-compatible display
                # while replacing its value with a marker plus correlation hash.
                clean[key] = "<redacted>"
                clean["command_sha256"] = hashlib.sha256(item.encode("utf-8")).hexdigest()
            else:
                clean[key] = sanitize_payload(item)
        return clean
    if isinstance(value, (list, tuple)):
        return [sanitize_payload(item) for item in value]
    return value


def _event_category(kind: str) -> str:
    if kind in {"host_read_file", "host_list_directory"}:
        return "file"
    if kind in {"host_write_file", "host_append_file", "host_replace_in_file", "host_make_directory"}:
        return "file"
    if kind == "host_search_text":
        return "file"
    if kind in {"host_run_command", "host_check_command"}:
        return "process"
    if kind == "host_knowledge":
        return "host"
    if kind.startswith("host_workspace_") or kind == "host_save_note":
        return "session"
    if kind.startswith("config"):
        return "configuration"
    return "api"


def _duration_ms(started_ts: Any, finished_ts: Any) -> float | None:
    if not isinstance(started_ts, str) or not isinstance(finished_ts, str):
        return None
    try:
        started = datetime.fromisoformat(started_ts.replace("Z", "+00:00"))
        finished = datetime.fromisoformat(finished_ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=timezone.utc)
    return max(0.0, round((finished - started).total_seconds() * 1000.0, 3))


def normalize_journal_record(
    record: Mapping[str, Any],
    *,
    inherited_kind: str | None = None,
    started_ts: str | None = None,
) -> dict[str, Any]:
    """Return a redacted, classification-rich view of one journal record.

    The field layout intentionally follows useful pieces of OpenTelemetry/ECS
    without claiming wire compatibility: severity uses OTel's normalized
    numbers, ``event_dataset`` identifies the stable source, ``event_category``
    describes what happened, and high-cardinality correlation stays in
    ``interaction_id`` rather than becoming a stream/category dimension.
    """
    item = dict(record)
    kind = str(item.get("kind") or inherited_kind or "unknown")
    event_type = str(item.get("type") or "event")
    ok_value = item.get("ok")
    if event_type == "op_started":
        severity_text = "DEBUG"
        outcome = "unknown"
        phase = "started"
    elif event_type == "op_result" and ok_value is True:
        severity_text = "INFO"
        outcome = "success"
        phase = "result"
    elif event_type == "op_result" and ok_value is False:
        severity_text = "ERROR"
        outcome = "failure"
        phase = "result"
    else:
        severity_text = "INFO"
        outcome = "unknown"
        phase = event_type.removeprefix("op_") or "event"

    item["journal_schema"] = JOURNAL_SCHEMA_VERSION
    item["log_source"] = JOURNAL_SOURCE
    item["event_dataset"] = JOURNAL_DATASET
    item["event_name"] = f"workspace.operation.{phase}"
    item["event_category"] = _event_category(kind)
    item["event_action"] = kind
    item["event_outcome"] = outcome
    item["operation_phase"] = phase
    item["severity_text"] = severity_text
    item["severity_number"] = _SEVERITY_NUMBERS[severity_text]
    if kind != "unknown":
        item.setdefault("kind", kind)
    if isinstance(item.get("op"), str):
        item["interaction_id"] = item["op"]
    duration = _duration_ms(started_ts, item.get("ts")) if phase == "result" else None
    if duration is not None:
        item["event_duration_ms"] = duration
    if "payload" in item:
        item["payload"] = sanitize_payload(item["payload"])
    return item


def normalize_journal_records(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Normalize a journal stream while correlating start/result pairs.

    Historical result records did not persist ``kind``. Correlating by ``op``
    repairs their action/category at read time and also derives operation
    duration without rewriting old journal files.
    """
    normalized: list[dict[str, Any]] = []
    starts: dict[str, tuple[str, str | None]] = {}
    for event in events:
        op = event.get("op")
        event_type = event.get("type")
        inherited_kind: str | None = None
        started_ts: str | None = None
        if isinstance(op, str) and event_type == "op_result":
            inherited_kind, started_ts = starts.get(op, (None, None))
        item = normalize_journal_record(
            event,
            inherited_kind=inherited_kind,
            started_ts=started_ts,
        )
        normalized.append(item)
        if not isinstance(op, str):
            continue
        if event_type == "op_started":
            kind = str(item.get("kind") or "unknown")
            ts = item.get("ts") if isinstance(item.get("ts"), str) else None
            starts[op] = (kind, ts)
        elif event_type == "op_result":
            starts.pop(op, None)
    return normalized


def summarize_journal_records(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = normalize_journal_records(events)
    categories: dict[str, int] = {}
    severities: dict[str, int] = {}
    outcomes: dict[str, int] = {}
    actions: dict[str, int] = {}
    for item in normalized:
        category = str(item.get("event_category") or "api")
        severity = str(item.get("severity_text") or "INFO")
        outcome = str(item.get("event_outcome") or "unknown")
        action = str(item.get("event_action") or "unknown")
        categories[category] = categories.get(category, 0) + 1
        severities[severity] = severities.get(severity, 0) + 1
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        actions[action] = actions.get(action, 0) + 1
    operations = sum(1 for item in normalized if item.get("operation_phase") == "result")
    failures = sum(1 for item in normalized if item.get("event_outcome") == "failure")
    return {
        "events": len(normalized),
        "operations": operations,
        "failures": failures,
        "categories": dict(sorted(categories.items())),
        "severities": dict(sorted(severities.items())),
        "outcomes": dict(sorted(outcomes.items())),
        "actions": dict(sorted(actions.items())),
    }


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
    return normalize_journal_records(records)


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
    event_list = normalize_journal_records(events)
    event_list.sort(key=lambda item: item["seq"] if isinstance(item.get("seq"), int) else float("inf"))

    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = ["# Workspace State", ""]
    for key in sorted(meta, key=str):
        shown = meta[key] if isinstance(meta[key], str) else json.dumps(
            meta[key], sort_keys=True, separators=(",", ":")
        )
        lines.append(f"- {cell(key)}: {cell(shown)}")

    summary = summarize_journal_records(event_list)
    category_text = ", ".join(
        f"{name}={count}" for name, count in summary["categories"].items()
    ) or "none"
    severity_text = ", ".join(
        f"{name}={count}" for name, count in summary["severities"].items()
    ) or "none"
    outcome_text = ", ".join(
        f"{name}={count}" for name, count in summary["outcomes"].items()
    ) or "none"
    lines.extend(
        [
            "",
            "## Log Summary",
            "",
            f"- events: {summary['events']}",
            f"- categories: {category_text}",
            f"- severities: {severity_text}",
            f"- outcomes: {outcome_text}",
            "",
            "## Pending Operations",
            "",
        ]
    )
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
            "| seq | ts | type | op | kind | ok | severity | category | outcome |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in event_list:
        ok_value = item.get("ok")
        ok_cell = "" if ok_value is None else cell(bool(ok_value)).lower()
        lines.append(
            "| {seq} | {ts} | {etype} | {op} | {kind} | {okc} | {severity} | {category} | {outcome} |".format(
                seq=cell(item.get("seq", "?")),
                ts=cell(item.get("ts", "?")),
                etype=cell(item.get("type", "?")),
                op=cell(item.get("op", "?")),
                kind=cell(item.get("kind", "?")),
                okc=ok_cell,
                severity=cell(item.get("severity_text", "INFO")),
                category=cell(item.get("event_category", "api")),
                outcome=cell(item.get("event_outcome", "unknown")),
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

    def create_or_bind(
        self,
        chat_id: str | None = None,
        *,
        label: str | None = None,
        resume_token: str | None = None,
        require_token: bool = False,
    ) -> BindResult:
        self.root.mkdir(parents=True, exist_ok=True)
        if chat_id is None:
            self._enforce_capacity()
            for _ in range(10):
                generated = generate_chat_id(label)
                with self._lock_for(generated):
                    ws = self.root / generated
                    try:
                        os.mkdir(ws)
                    except FileExistsError:
                        continue
                    return self._initialize(generated, ws)
            raise CapacityError("Unable to allocate a unique workspace directory.")

        validated = validate_chat_id(chat_id)
        with self._lock_for(validated):
            ws = self.root / validated
            if not ws.exists():
                self._enforce_capacity()
            try:
                os.mkdir(ws)
            except FileExistsError:
                return self._bind_existing(
                    validated,
                    ws,
                    resume_token=resume_token,
                    require_token=require_token,
                )
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
        raw_token, token_hash = generate_session_token()
        meta = {
            "chat_id": chat_id,
            "created_at": _utc_now_iso(),
            "schema": WORKSPACE_SCHEMA,
            "token_hash": token_hash,
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
        return BindResult(
            path=ws,
            created=True,
            resumed_hint=None,
            chat_id=chat_id,
            session_token=raw_token,
        )

    def _bind_existing(
        self,
        chat_id: str,
        ws: Path,
        *,
        resume_token: str | None = None,
        require_token: bool = False,
    ) -> BindResult:
        deadline = time.monotonic() + self.bind_wait_seconds
        while True:
            if (ws / META_NAME).exists():
                meta = load_workspace_meta(ws, expected_chat_id=chat_id)
                token_hash = meta.get("token_hash")
                if token_hash and (require_token or resume_token is not None):
                    if not resume_token or not verify_session_token(resume_token, token_hash):
                        raise ResumeUnauthorizedError(
                            f"Invalid or missing resume_token for workspace '{chat_id}'.",
                            chat_id=chat_id,
                        )
                # Ownership first (squat defense), then quota, before any write.
                self._enforce_quota(ws, chat_id)
                return BindResult(
                    path=ws,
                    created=False,
                    resumed_hint=self._resume_hint(ws),
                    chat_id=chat_id,
                    session_token=resume_token,
                )
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
        *,
        kind: str | None = None,
    ) -> dict[str, Any]:
        base = {
            "type": "op_result",
            "op": str(op_id),
            "ok": bool(ok),
            "payload": sanitize_payload({} if payload is None else payload),
        }
        if kind is not None:
            base["kind"] = str(kind)
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
            # is what would grow the footprint past the quota. The gate must
            # also stay ahead of the next_seq bump so a refusal burns no seq.
            self._enforce_quota(ws, validated, len(encoded))
            if rotates and self._needs_rotation(journal, len(encoded)):
                unresolved = pending_operations(read_journal_records(ws))
                os.replace(journal, ws / JOURNAL_ARCHIVE_NAME)
                # The replace destroys the previous archive generation, taking
                # any still-unresolved op_started record with it: re-append
                # them verbatim (original seq/ts/kind/payload) into the fresh
                # journal so pending tracking survives unlimited rotations.
                if unresolved:
                    descriptor = os.open(
                        journal, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600
                    )
                    try:
                        for pending_record in unresolved:
                            os.write(descriptor, _json_line_bytes(pending_record))
                    finally:
                        os.close(descriptor)
            # Bump next_seq before the journal write: a kill in between then
            # skips a seq (visible gap) instead of letting the next append
            # reuse one already on disk.
            meta["next_seq"] = int(meta["next_seq"]) + 1
            _atomic_write(ws / META_NAME, _json_line_bytes(meta))
            descriptor = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(descriptor, encoded)
            finally:
                os.close(descriptor)
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
