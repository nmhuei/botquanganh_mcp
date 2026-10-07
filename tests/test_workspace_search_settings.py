"""Settings validation and persistence (Task 6, RED)."""

from __future__ import annotations

from pathlib import Path


def test_search_settings_validate_and_persist_atomically(tmp_path):
    from app.cli.config_view import read_env, set_operational_config

    (tmp_path / ".env").write_text("MCP_PORT=18427\n", encoding="utf-8")
    result = set_operational_config(
        tmp_path,
        {
            "WORKSPACE_SEARCH_MAX_CONCURRENT": "2",
            "SEARCH_TEXT_DEADLINE_SECONDS": "5",
        },
    )
    assert result["WORKSPACE_SEARCH_MAX_CONCURRENT"] == "2"
    assert float(read_env(tmp_path)["SEARCH_TEXT_DEADLINE_SECONDS"]) == 5.0


def test_search_settings_reject_invalid_values(tmp_path):
    import pytest
    from app.cli.config_view import set_operational_config

    (tmp_path / ".env").write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        set_operational_config(tmp_path, {"WORKSPACE_SEARCH_MAX_CONCURRENT": "0"})


def test_desktop_settings_payload_includes_search_limits():
    from app.cli.config_view import rust_settings_payload

    assert "WORKSPACE_SEARCH_MAX_CONCURRENT" in rust_settings_payload()
    assert "SEARCH_TEXT_DEADLINE_SECONDS" in rust_settings_payload()
    assert "MCP_MAX_PAYLOAD_BYTES" in rust_settings_payload()
