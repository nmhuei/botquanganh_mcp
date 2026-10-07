"""In-memory workspace binding registry for Level 4 attribution.

Maintains thread-safe bindings for active workspace sessions in the server process.
Ensures operational tool calls require a prior successful workspace_context(bind).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_LOCK = threading.RLock()
# Maps (canonical_root_str, chat_id) -> {"created_at": str | None, "bound_at": str}
_BINDINGS: dict[tuple[str, str], dict[str, Any]] = {}


def _normalize_root(root: Path | str) -> str:
    """Return canonical path string for root directory."""
    try:
        return str(Path(root).expanduser().resolve())
    except Exception:
        return str(root)


def register_workspace_binding(
    root: Path | str, chat_id: str, created_at: Optional[str] = None
) -> None:
    """Record an active workspace binding in memory."""
    key = (_normalize_root(root), str(chat_id).strip())
    now_iso = datetime.now(timezone.utc).isoformat()
    with _LOCK:
        _BINDINGS[key] = {
            "created_at": created_at,
            "bound_at": now_iso,
        }


def has_workspace_binding(root: Path | str, chat_id: str) -> bool:
    """Return True if workspace key is registered in server memory."""
    key = (_normalize_root(root), str(chat_id).strip())
    with _LOCK:
        return key in _BINDINGS


def validate_workspace_binding(root: Path | str, chat_id: str) -> bool:
    """Verify that workspace is registered and matches on-disk metadata."""
    key = (_normalize_root(root), str(chat_id).strip())
    with _LOCK:
        entry = _BINDINGS.get(key)
        if entry is None:
            return False

    meta_file = Path(_normalize_root(root)) / str(chat_id).strip() / "meta.json"
    if not meta_file.is_file():
        forget_workspace_binding(root, chat_id)
        return False

    expected_created = entry.get("created_at")
    if expected_created:
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            actual_created = meta.get("created_at")
            if actual_created and actual_created != expected_created:
                forget_workspace_binding(root, chat_id)
                return False
        except Exception:
            forget_workspace_binding(root, chat_id)
            return False

    return True


def forget_workspace_binding(root: Path | str, chat_id: str) -> None:
    """Remove workspace binding from server memory."""
    key = (_normalize_root(root), str(chat_id).strip())
    with _LOCK:
        _BINDINGS.pop(key, None)


def clear_workspace_bindings() -> None:
    """Clear all bindings. Used for testing and server reset."""
    with _LOCK:
        _BINDINGS.clear()
