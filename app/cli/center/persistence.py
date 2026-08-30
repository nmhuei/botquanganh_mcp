"""XDG state persistence for non-preference desktop state."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping


STATE_SCHEMA_VERSION = 1
DEFAULT_WINDOW_STATE: dict[str, Any] = {
    "schema_version": STATE_SCHEMA_VERSION,
    "active_tab": "runtime",
    "geometry": "1180x760",
    "activity_pane": None,
    "logs_pane": None,
    "selected_session": None,
    "inspector_tabs": {},
}


def default_center_state_path() -> Path:
    configured = os.environ.get("XDG_STATE_HOME", "").strip()
    base = Path(configured).expanduser() if configured else Path.home() / ".local" / "state"
    return base / "bqa-center" / "window.json"


class CenterWindowStateStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_center_state_path()

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(DEFAULT_WINDOW_STATE)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return dict(DEFAULT_WINDOW_STATE)
        if not isinstance(raw, dict):
            return dict(DEFAULT_WINDOW_STATE)
        result = dict(DEFAULT_WINDOW_STATE)
        result.update(raw)
        result["schema_version"] = STATE_SCHEMA_VERSION
        return result

    def save(self, values: Mapping[str, Any]) -> None:
        data = dict(DEFAULT_WINDOW_STATE)
        data.update(dict(values))
        data["schema_version"] = STATE_SCHEMA_VERSION
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=".window.",
            suffix=".json",
            dir=self.path.parent,
            text=True,
        )
        temporary_path = Path(temporary)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self.path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
