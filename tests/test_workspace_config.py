import pytest
from dotenv import dotenv_values

from app.cli.config_view import set_workspace_config


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
