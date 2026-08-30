import json

import pytest

from app.cli.ui_preferences import (
    UIPreferencesError,
    UIPreferencesStore,
    default_ui_preferences_path,
    normalize_ui_language,
)


def test_ui_preferences_default_path_follows_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_ui_preferences_path() == tmp_path / "bqa-center" / "ui.json"


def test_ui_preferences_store_persists_language_without_touching_env(tmp_path):
    path = tmp_path / "ui.json"
    store = UIPreferencesStore(path)

    assert store.set_language("vi") == "vi"

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["language"] == "vi"
    assert payload["schema_version"] == 1
    assert (path.stat().st_mode & 0o777) == 0o600


def test_ui_preferences_preserves_future_unknown_keys(tmp_path):
    path = tmp_path / "ui.json"
    path.write_text(
        '{"schema_version":1,"language":"en","font_scale":1.25}',
        encoding="utf-8",
    )
    store = UIPreferencesStore(path)

    store.set_language("vi")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["language"] == "vi"
    assert payload["font_scale"] == 1.25


def test_ui_preferences_migrates_legacy_language_only_when_store_missing(tmp_path):
    path = tmp_path / "ui.json"
    store = UIPreferencesStore(path)

    first = store.load(legacy_language="vi")
    second = store.load(legacy_language="en")

    assert first["language"] == "vi"
    assert second["language"] == "vi"
    assert json.loads(path.read_text(encoding="utf-8"))["language"] == "vi"


def test_ui_preferences_invalid_legacy_value_falls_back_without_blocking_ui(tmp_path):
    path = tmp_path / "ui.json"
    store = UIPreferencesStore(path)

    values = store.load(legacy_language="fr")

    assert values["language"] == "en"
    assert json.loads(path.read_text(encoding="utf-8"))["language"] == "en"


def test_ui_preferences_rejects_invalid_saved_language(tmp_path):
    path = tmp_path / "ui.json"
    path.write_text('{"language":"fr"}', encoding="utf-8")

    with pytest.raises(UIPreferencesError, match="en or vi"):
        UIPreferencesStore(path).load()


def test_normalize_ui_language_accepts_only_supported_values():
    assert normalize_ui_language(" EN ") == "en"
    assert normalize_ui_language("vi") == "vi"
    with pytest.raises(UIPreferencesError, match="en or vi"):
        normalize_ui_language("fr")


def test_backend_config_does_not_own_desktop_language():
    from app.cli.config_view import DEFAULTS

    assert "BQA_UI_LANGUAGE" not in DEFAULTS
