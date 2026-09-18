import pytest
import app.config


@pytest.fixture(autouse=True)
def _isolate_default_host_scopes(monkeypatch):
    """Ensure unit tests do not accidentally inherit host-specific scopes from developer .env."""
    monkeypatch.setenv("HOST_READ_SCOPE", "")
    monkeypatch.setenv("HOST_WRITE_SCOPE", "")
    monkeypatch.setattr(app.config, "HOST_READ_SCOPE_SET", False)
    monkeypatch.setattr(app.config, "HOST_WRITE_SCOPE_SET", False)
    monkeypatch.setattr(app.config, "HOST_READ_DENY_GLOBS", [])
