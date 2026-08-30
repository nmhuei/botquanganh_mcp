"""Desktop-only preferences for BQA Center.

UI preferences intentionally live outside the server .env so changing language,
theme, font scale, or future presentation options never requires a backend
restart.  The store follows XDG on Linux and uses an atomic JSON write.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping


UI_PREFERENCES_SCHEMA = 1
DEFAULT_UI_LANGUAGE = "en"
SUPPORTED_UI_LANGUAGES = ("en", "vi")
DEFAULT_UI_PREFERENCES: dict[str, Any] = {
    "schema_version": UI_PREFERENCES_SCHEMA,
    "language": DEFAULT_UI_LANGUAGE,
}


class UIPreferencesError(ValueError):
    """Raised when UI preferences cannot be loaded, validated, or saved."""


def default_ui_preferences_path() -> Path:
    """Return the per-user XDG path used by BQA Center UI preferences."""
    configured = os.environ.get("XDG_CONFIG_HOME", "").strip()
    base = Path(configured).expanduser() if configured else Path.home() / ".config"
    return base / "bqa-center" / "ui.json"


def normalize_ui_language(value: object) -> str:
    """Return one supported UI language or reject the value explicitly."""
    language = str(value or DEFAULT_UI_LANGUAGE).strip().lower()
    if language not in SUPPORTED_UI_LANGUAGES:
        raise UIPreferencesError("UI language must be en or vi.")
    return language


class UIPreferencesStore:
    """Small atomic JSON store for presentation-only settings."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_ui_preferences_path()

    def _normalized(self, raw: Mapping[str, Any] | None) -> dict[str, Any]:
        data = dict(DEFAULT_UI_PREFERENCES)
        if raw:
            # Keep unknown keys so future UI settings survive an older build.
            data.update(dict(raw))
        data["schema_version"] = UI_PREFERENCES_SCHEMA
        data["language"] = normalize_ui_language(data.get("language"))
        return data

    def load(
        self,
        *,
        legacy_language: object | None = None,
        migrate_legacy: bool = True,
    ) -> dict[str, Any]:
        """Load preferences, optionally migrating the old .env language once."""
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise UIPreferencesError(
                    f"Unable to read UI preferences: {exc}"
                ) from exc
            if not isinstance(raw, dict):
                raise UIPreferencesError("UI preferences must contain a JSON object.")
            return self._normalized(raw)

        data = dict(DEFAULT_UI_PREFERENCES)
        if legacy_language not in {None, ""}:
            try:
                data["language"] = normalize_ui_language(legacy_language)
            except UIPreferencesError:
                # A stale/invalid legacy server setting must not prevent the UI
                # from opening; the new UI store starts from the supported default.
                data["language"] = DEFAULT_UI_LANGUAGE
        data = self._normalized(data)
        if migrate_legacy and legacy_language not in {None, ""}:
            self.save(data)
        return data

    def save(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Atomically replace the UI preference JSON with normalized values."""
        data = self._normalized(values)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(
                prefix=".ui.",
                suffix=".json",
                dir=self.path.parent,
                text=True,
            )
            temporary_path = Path(temporary)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(
                        data,
                        handle,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(temporary_path, 0o600)
                os.replace(temporary_path, self.path)
            except Exception:
                temporary_path.unlink(missing_ok=True)
                raise
        except OSError as exc:
            raise UIPreferencesError(
                f"Unable to save UI preferences: {exc}"
            ) from exc
        return data

    def update(self, **updates: Any) -> dict[str, Any]:
        """Merge and save presentation-only settings without touching .env."""
        current = self.load(migrate_legacy=False)
        current.update(updates)
        return self.save(current)

    def set_language(self, language: object) -> str:
        """Persist and return a normalized language immediately."""
        normalized = normalize_ui_language(language)
        self.update(language=normalized)
        return normalized
