import pytest
from dotenv import dotenv_values

from app.config import _load_env_file
from app.cli.config_view import (
    DEFAULTS,
    set_desktop_ui_language,
    set_workspace_config,
    validate_config,
)


def test_set_workspace_config_updates_both_workspace_settings_and_preserves_lines(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("HOST_WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("HOST_DEFAULT_DIR", raising=False)
    selected = tmp_path / "CTF Workspace"
    selected.mkdir()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "REQUIRE_AUTH=false\nHOST_WORKSPACE_DIR=/old\n# keep this comment\n",
        encoding="utf-8",
    )

    updates = set_workspace_config(tmp_path, str(selected))

    values = dotenv_values(env_file)
    assert updates == {
        "HOST_WORKSPACE_DIR": str(selected),
        "HOST_DEFAULT_DIR": str(selected),
    }
    assert values["HOST_WORKSPACE_DIR"] == str(selected)
    assert values["HOST_DEFAULT_DIR"] == str(selected)
    assert "REQUIRE_AUTH=false" in env_file.read_text(encoding="utf-8")
    assert "# keep this comment" in env_file.read_text(encoding="utf-8")


def test_set_workspace_config_rejects_missing_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("HOST_WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("HOST_DEFAULT_DIR", raising=False)
    with pytest.raises(ValueError, match="existing directory"):
        set_workspace_config(tmp_path, str(tmp_path / "missing"))


def test_set_workspace_config_rejects_an_environment_override(tmp_path, monkeypatch):
    selected = tmp_path / "workspace"
    selected.mkdir()
    monkeypatch.setenv("HOST_WORKSPACE_DIR", str(tmp_path / "forced"))
    with pytest.raises(ValueError, match="current environment"):
        set_workspace_config(tmp_path, str(selected))


def test_set_desktop_ui_language_persists_the_official_setting(tmp_path, monkeypatch):
    monkeypatch.delenv("BQA_UI_LANGUAGE", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("REQUIRE_AUTH=false\n", encoding="utf-8")

    assert set_desktop_ui_language(tmp_path, "vi") == {"BQA_UI_LANGUAGE": "vi"}
    assert 'BQA_UI_LANGUAGE="vi"' in env_file.read_text(encoding="utf-8")


def test_set_desktop_ui_language_allows_a_value_loaded_from_dotenv(tmp_path, monkeypatch):
    """A `.env` loader value is not an operator's shell override."""
    monkeypatch.delenv("BQA_UI_LANGUAGE", raising=False)
    source_env = tmp_path / "source.env"
    source_env.write_text('BQA_UI_LANGUAGE="en"\n', encoding="utf-8")
    _load_env_file(source_env)

    target_env = tmp_path / ".env"
    target_env.write_text('BQA_UI_LANGUAGE="en"\n', encoding="utf-8")

    assert set_desktop_ui_language(tmp_path, "vi") == {"BQA_UI_LANGUAGE": "vi"}
    assert 'BQA_UI_LANGUAGE="vi"' in target_env.read_text(encoding="utf-8")


def test_desktop_ui_language_rejects_invalid_value_and_environment_override(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("BQA_UI_LANGUAGE", "vi")
    with pytest.raises(ValueError, match="current environment"):
        set_desktop_ui_language(tmp_path, "vi")

    monkeypatch.delenv("BQA_UI_LANGUAGE")
    with pytest.raises(ValueError, match="en or vi"):
        set_desktop_ui_language(tmp_path, "fr")

    checks = {
        item["name"]: item
        for item in validate_config(
            tmp_path,
            {**DEFAULTS, "BQA_UI_LANGUAGE": "fr"},
        )
    }
    assert checks["config_bqa_ui_language"] == {
        "name": "config_bqa_ui_language",
        "status": "fail",
        "message": "fr; expected en or vi",
    }
