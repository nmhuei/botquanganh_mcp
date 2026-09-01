import json

from app.cli.center.persistence import (
    CenterWindowStateStore,
    default_center_state_path,
)


def test_window_state_default_path_uses_xdg_state_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert default_center_state_path() == tmp_path / "bqa-center" / "window.json"


def test_window_state_store_round_trips_and_preserves_unknown_keys(tmp_path):
    path = tmp_path / "window.json"
    store = CenterWindowStateStore(path)
    store.save(
        {
            "geometry": "1366x768",
            "active_tab": "gpt_activity",
            "selected_session": "chat-a",
            "future_key": {"keep": True},
        }
    )

    loaded = store.load()

    assert loaded["geometry"] == "1366x768"
    assert loaded["active_tab"] == "gpt_activity"
    assert loaded["selected_session"] == "chat-a"
    assert loaded["future_key"] == {"keep": True}
    assert (path.stat().st_mode & 0o777) == 0o600


def test_window_state_corruption_falls_back_to_defaults(tmp_path):
    path = tmp_path / "window.json"
    path.write_text("{broken", encoding="utf-8")

    loaded = CenterWindowStateStore(path).load()

    assert loaded["geometry"] == "1280x820"
    assert loaded["active_tab"] == "overview"


def test_window_state_json_has_schema_version(tmp_path):
    path = tmp_path / "window.json"
    CenterWindowStateStore(path).save({"active_tab": "workspace_logs"})
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
