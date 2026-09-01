"""Per-chat identity binding and workspace registry (Wave 1B foundation).

The request path uses this module to validate and bind chat identities,
annotate host operations, and enforce attribution policy. It provides:

- verbatim chat-id validation (no trimming, no case folding),
- ContextVar-based binding that mirrors ``app.request_context`` conventions,
- a thread-safe LRU registry of known chats,
- defensive access to the ``ATTRIBUTION_MODE`` configuration value.

Configuration reads stay defensive through ``getattr`` so tests and partial
embedders without newer settings still fall back safely to ``off``.
"""

from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

CHAT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{5,63}$")

REGISTRY_CAPACITY = 64
DEFAULT_ATTRIBUTION_MODE = "off"
ENFORCED_ATTRIBUTION_MODE = "enforce"
# Mirrors the validated set in app.config (off/tag/strict/enforce) plus the
# legacy "on" alias kept so earlier-wave callers keep resolving; anything
# unknown or missing still degrades to "off".
KNOWN_ATTRIBUTION_MODES = frozenset({"off", "on", "tag", "strict", "enforce"})

_CHAT_ID: ContextVar[str | None] = ContextVar("bqa_chat_id", default=None)

_REGISTRY_LOCK = threading.Lock()
_REGISTRY: OrderedDict[str, dict[str, int]] = OrderedDict()


class InvalidChatId(ValueError):
    """Raised when a chat identifier fails the validation pattern."""


def validate_chat_id(chat_id: str) -> str:
    """Return ``chat_id`` only when it matches the pattern verbatim."""
    if not isinstance(chat_id, str) or not CHAT_ID_PATTERN.fullmatch(chat_id):
        raise InvalidChatId(
            "chat id must match ^[A-Za-z0-9][A-Za-z0-9._-]{5,63}$ "
            f"(6-64 chars, starting alphanumeric); got: {chat_id!r}"
        )
    return chat_id


def bind_chat(chat_id: str) -> Token[str | None]:
    """Validate and bind ``chat_id`` for the current context."""
    validate_chat_id(chat_id)
    return _CHAT_ID.set(chat_id)


def get_chat_id() -> str | None:
    """Return the bound chat id for this context, if any."""
    return _CHAT_ID.get()


def get_active_workspace() -> str | None:
    """Return the currently bound chat ID or fallback to the latest active workspace."""
    bound = get_chat_id()
    if bound:
        return bound

    # Check in-memory registry for most recently used
    with _REGISTRY_LOCK:
        if _REGISTRY:
            return next(reversed(_REGISTRY))

    # Check on-disk .last_session pointer if workspace infra is configured
    try:
        from pathlib import Path
        import json
        import app.config as config_module

        root_val = getattr(config_module, "HOST_CHAT_ROOT", "")
        if root_val:
            pointer_file = Path(root_val) / ".last_session"
            if pointer_file.is_file():
                data = json.loads(pointer_file.read_text(encoding="utf-8"))
                candidate = data.get("chat_id")
                if isinstance(candidate, str) and (Path(root_val) / candidate / "meta.json").is_file():
                    return candidate
    except Exception:
        pass

    return None



@contextmanager
def bound_chat(chat_id: str) -> Iterator[str]:
    """Bind ``chat_id`` for the block and restore the previous binding on exit."""
    token = bind_chat(chat_id)
    try:
        yield chat_id
    finally:
        _CHAT_ID.reset(token)


def touch_chat(chat_id: str, *, now: float | None = None) -> dict[str, int]:
    """Register a chat or refresh its ``last_seen``, returning a copy.

    Entries are kept in least-recently-used order inside a lock; touching an
    entry moves it to the most-recently-used end and the oldest entry is
    evicted once the registry exceeds :data:`REGISTRY_CAPACITY`.
    """
    validate_chat_id(chat_id)
    timestamp = int(time.time() if now is None else now)
    with _REGISTRY_LOCK:
        entry = _REGISTRY.get(chat_id)
        if entry is None:
            entry = {"first_seen": timestamp, "last_seen": timestamp}
            _REGISTRY[chat_id] = entry
        else:
            entry["last_seen"] = timestamp
            _REGISTRY.move_to_end(chat_id)
        while len(_REGISTRY) > REGISTRY_CAPACITY:
            _REGISTRY.popitem(last=False)
        return dict(entry)


def registered_chats() -> dict[str, dict[str, int]]:
    """Return a snapshot of the registry in LRU order (oldest first)."""
    with _REGISTRY_LOCK:
        return {chat_id: dict(entry) for chat_id, entry in _REGISTRY.items()}


def _raw_attribution_mode() -> Any:
    """Read ``ATTRIBUTION_MODE`` defensively from the config module.

    The attribute is added by a concurrent change, so it may legitimately be
    absent; a settings-object placement is tolerated as well.
    """
    from app import config as config_module

    raw = getattr(config_module, "ATTRIBUTION_MODE", None)
    if raw is None:
        settings_obj = getattr(config_module, "settings", None)
        if settings_obj is not None:
            raw = getattr(settings_obj, "ATTRIBUTION_MODE", None)
    return raw


def attribution_mode() -> str:
    """Return the effective attribution mode, defaulting to "off"."""
    raw = _raw_attribution_mode()
    mode = str(raw).strip().lower()
    return mode if mode in KNOWN_ATTRIBUTION_MODES else DEFAULT_ATTRIBUTION_MODE


def is_enforcing() -> bool:
    """True only when the effective attribution mode is ``"enforce"``.

    Enforce mode is the hardest attribution level: every HOST_TOOLS
    entry-point requires a valid, bound chat identity before doing any work.
    The wire contract (E6 BIND_REQUIRED, the single ``host_workspace_bind``
    exemption) is defined in :mod:`app.chat_errors`; tool-layer gating
    switches on this helper alone.
    """
    return attribution_mode() == ENFORCED_ATTRIBUTION_MODE


def annotate(record: dict[str, Any]) -> dict[str, Any]:
    """Stamp the bound chat id onto a journal record.

    Strict no-op while attribution is "off": the exact input object is
    returned unchanged with no added keys.  When enabled but no chat id is
    bound in the current context, nothing can be attributed and the record is
    likewise returned unchanged.
    """
    if attribution_mode() == "off":
        return record
    chat_id = get_chat_id()
    if not chat_id:
        return record
    record["chat_id"] = chat_id
    return record
