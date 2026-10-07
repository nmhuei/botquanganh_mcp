"""Workspace search configuration contract (Task 1, RED)."""

from __future__ import annotations

import importlib
from pathlib import Path

import app.config
from app.cli import config_view


REQUIRED_SEARCH_KEYS = {
    "WORKSPACE_SEARCH_MAX_WORK_MATCHES",
    "WORKSPACE_SEARCH_MAX_SCANNED_FILES",
    "WORKSPACE_SEARCH_MAX_SCANNED_BYTES",
    "WORKSPACE_SEARCH_MAX_CONCURRENT",
    "WORKSPACE_SEARCH_MAX_PER_CHAT",
    "WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS",
    "WORKSPACE_SEARCH_DEFAULT_MAX_MATCHES",
    "WORKSPACE_SEARCH_MAX_RETURNED_MATCHES",
    "WORKSPACE_SEARCH_MAX_LINE_CHARS",
    "MCP_MAX_PAYLOAD_BYTES",
    "MCP_TOOL_RESULT_OVERHEAD_BYTES",
}


def test_workspace_search_limits_are_validated(monkeypatch):
    monkeypatch.setenv("WORKSPACE_SEARCH_MAX_WORK_MATCHES", "0")
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-c", "import app.config"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode != 0
    assert "WORKSPACE_SEARCH_MAX_WORK_MATCHES" in proc.stderr


def test_workspace_search_keys_have_env_and_cli_parity():
    env_path = Path(__file__).resolve().parents[1] / ".env.example"
    env_keys = {
        line.split("=", 1)[0].strip()
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if line and not line.lstrip().startswith("#") and "=" in line
    }
    assert REQUIRED_SEARCH_KEYS <= env_keys
    assert REQUIRED_SEARCH_KEYS <= set(config_view.DEFAULTS)


def test_search_config_values_are_finite_positive():
    assert app.config.WORKSPACE_SEARCH_MAX_WORK_MATCHES >= 1
    assert app.config.WORKSPACE_SEARCH_MAX_SCANNED_FILES >= 1
    assert app.config.WORKSPACE_SEARCH_MAX_SCANNED_BYTES >= 1
    assert app.config.WORKSPACE_SEARCH_MAX_CONCURRENT >= 1
    assert app.config.WORKSPACE_SEARCH_MAX_PER_CHAT >= 1
    assert app.config.WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS >= 0
    assert app.config.WORKSPACE_SEARCH_DEFAULT_MAX_MATCHES >= 1
    assert app.config.WORKSPACE_SEARCH_MAX_RETURNED_MATCHES >= 1
    assert app.config.WORKSPACE_SEARCH_MAX_LINE_CHARS >= 1
    assert app.config.MCP_MAX_PAYLOAD_BYTES >= 1024
    assert app.config.MCP_TOOL_RESULT_OVERHEAD_BYTES >= 0
    assert (
        app.config.WORKSPACE_SEARCH_DEFAULT_MAX_MATCHES
        <= app.config.WORKSPACE_SEARCH_MAX_RETURNED_MATCHES
    )
