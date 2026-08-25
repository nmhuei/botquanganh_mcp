import logging

import pytest

import app.config
import app.logging_audit


@pytest.fixture()
def isolated_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", workspace.resolve())
    monkeypatch.setattr(app.config, "HOST_DEFAULT_DIR", workspace.resolve())
    monkeypatch.setattr(app.config, "HOST_RESTRICT_TO_WORKSPACE", True)
    quiet = logging.getLogger("strength-audit-null")
    quiet.addHandler(logging.NullHandler())
    quiet.propagate = False
    monkeypatch.setattr(app.logging_audit, "logger", quiet)
    return workspace
