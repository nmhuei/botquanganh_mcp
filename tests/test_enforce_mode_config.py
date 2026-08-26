"""B1: ``ATTRIBUTION_MODE="enforce"`` acceptance plus the E6 BIND_REQUIRED contract.

Covers the three layers that define the enforce wire contract:

- app/config.py accepts "enforce" (and keeps rejecting garbage),
- app/chat_identity.py resolves it through ``attribution_mode`` /
  ``is_enforcing`` across every raw-value shape,
- app/chat_errors.py ships E6 BIND_REQUIRED with copy-safe rendering and
  the semantic-contract block the tool layer gates against.
"""

import inspect
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

import app.config
from app import chat_identity
from app.chat_errors import (
    CHAT_ERROR_CATALOG,
    ChatCatalogError,
    chat_error_payload,
    to_tool_error,
)
from app.chat_identity import attribution_mode, is_enforcing

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Config layer: ATTRIBUTION_MODE accepts "enforce".
#
# Subprocess-isolated because app.config loads exactly once per interpreter.
# ---------------------------------------------------------------------------


def _run_config_probe(env_value):
    env = dict(os.environ)
    env.pop("ATTRIBUTION_MODE", None)
    if env_value is not None:
        env["ATTRIBUTION_MODE"] = env_value
    return subprocess.run(  # nosec B603
        [sys.executable, "-c", "import app.config as c; print(c.ATTRIBUTION_MODE)"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=120,
    )


@pytest.mark.parametrize("raw", ["enforce", "ENFORCE", "  Enforce  "])
def test_config_accepts_enforce_and_normalizes(raw):
    proc = _run_config_probe(raw)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "enforce"


def test_config_default_remains_off():
    proc = _run_config_probe(None)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "off"


@pytest.mark.parametrize(
    "garbage", ["loud", "", "enforcel", "enforce,off", "0", "strict enforce"]
)
def test_config_still_rejects_garbage_values(garbage):
    proc = _run_config_probe(garbage)
    assert proc.returncode != 0
    assert "ATTRIBUTION_MODE" in proc.stderr


# ---------------------------------------------------------------------------
# Identity layer: is_enforcing() matrix across every raw-value shape.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected_mode", "expected_enforcing"),
    [
        ("off", "off", False),
        ("OFF", "off", False),
        (" off ", "off", False),
        ("", "off", False),
        (None, "off", False),  # config attribute entirely absent
        ("banana", "off", False),  # unknown value degrades to off
        ("on", "on", False),  # legacy alias stays recognized, never enforcing
        ("tag", "tag", False),
        ("STRICT", "strict", False),
        ("enforce", "enforce", True),
        (" ENFORCE ", "enforce", True),
    ],
)
def test_is_enforcing_matrix(monkeypatch, raw, expected_mode, expected_enforcing):
    monkeypatch.setattr(chat_identity, "_raw_attribution_mode", lambda: raw)
    assert attribution_mode() == expected_mode
    assert is_enforcing() is expected_enforcing


def test_is_enforcing_reads_the_real_config_attribute(monkeypatch):
    # No stubbing: exercise the defensive getattr path against app.config.
    monkeypatch.setattr(app.config, "ATTRIBUTION_MODE", "enforce")
    assert is_enforcing() is True
    monkeypatch.setattr(app.config, "ATTRIBUTION_MODE", "strict")
    assert is_enforcing() is False


def test_is_enforcing_when_config_attribute_is_deleted(monkeypatch):
    monkeypatch.delattr(app.config, "ATTRIBUTION_MODE", raising=False)
    assert attribution_mode() == "off"
    assert is_enforcing() is False


def test_known_modes_are_a_superset_of_the_config_set():
    assert {"off", "tag", "strict", "enforce"} <= chat_identity.KNOWN_ATTRIBUTION_MODES
    assert chat_identity.ENFORCED_ATTRIBUTION_MODE == "enforce"
    assert chat_identity.DEFAULT_ATTRIBUTION_MODE == "off"


# ---------------------------------------------------------------------------
# Error layer: E6 BIND_REQUIRED copy safety and rendering.
# ---------------------------------------------------------------------------


def test_catalog_ships_e6_bind_required():
    entry = CHAT_ERROR_CATALOG.get("E6")
    assert entry is not None
    assert entry.name == "BIND_REQUIRED"
    assert "host_workspace_bind" in entry.template
    assert "\n" not in entry.template


def test_e6_renders_single_line_with_validated_chat_id():
    payload = chat_error_payload("E6", chat_id="abcdef")
    error = payload["error"]
    assert payload["ok"] is False
    assert error["code"] == "E6"
    assert error["name"] == "BIND_REQUIRED"
    assert "abcdef" in error["message"]
    assert "host_workspace_bind" in error["message"]
    assert "\n" not in error["message"]
    assert error["suggestion"]


def test_e6_missing_fields_degrade_to_placeholders_without_raising():
    payload = chat_error_payload("E6")
    assert payload["error"]["code"] == "E6"
    assert payload["error"]["message"]  # placeholder "?" fills {chat_id}


class HostileField:
    """A value whose every rendering path explodes."""

    def __format__(self, spec):
        raise RuntimeError("format boom")

    def __str__(self):
        raise RuntimeError("str boom")


def test_e6_never_raises_on_hostile_field_objects():
    payload = chat_error_payload("E6", chat_id=HostileField())
    error = payload["error"]
    assert error["code"] == "E6"
    assert "boom" not in error["message"]  # degraded via the _SafeField guard
    assert error["message"].endswith(".")


def test_invalid_ids_cannot_leak_through_the_catalog():
    # The invalid-id path is E1, whose template interpolates nothing, so raw
    # rejected input can never reach any message; only validated ids may be
    # passed to E6's {chat_id} field.
    e1_entry = CHAT_ERROR_CATALOG["E1"]
    assert "{chat_id}" not in e1_entry.template
    payload = chat_error_payload("E1", chat_id="../escape <script>")
    assert "../escape" not in payload["error"]["message"]


# ---------------------------------------------------------------------------
# Error layer: E6 wiring through the catalog mapping helpers.
# ---------------------------------------------------------------------------


def test_to_tool_error_passes_e6_catalog_errors_through():
    payload = to_tool_error(ChatCatalogError("E6", chat_id="abcdef"))
    assert payload["error"]["code"] == "E6"
    assert payload["error"]["name"] == "BIND_REQUIRED"
    assert "abcdef" in payload["error"]["message"]


def make_fake_workspace_module(**extra_names):
    module = types.ModuleType("app.chat_workspace")

    class BindRequiredError(Exception):
        pass

    module.BindRequiredError = BindRequiredError
    for name, value in extra_names.items():
        setattr(module, name, value)
    return module, BindRequiredError


def test_to_tool_error_maps_explicit_bind_exception_onto_e6(monkeypatch):
    module, BindRequiredError = make_fake_workspace_module()
    monkeypatch.setitem(sys.modules, "app.chat_workspace", module)

    exc = BindRequiredError("not bound")
    exc.chat_id = "abcdef"
    payload = to_tool_error(exc)

    assert payload["error"]["code"] == "E6"
    assert "abcdef" in payload["error"]["message"]


def test_to_tool_error_name_fragment_backstop_maps_bind_exceptions_onto_e6(
    monkeypatch,
):
    # Infra missing entirely: classification must still work off the class
    # name alone (the documented "Bind" fragment rule).
    monkeypatch.setitem(sys.modules, "app.chat_workspace", None)

    class WorkspaceBindRequiredError(Exception):
        pass

    payload = to_tool_error(WorkspaceBindRequiredError("unbound"))

    assert payload["error"]["code"] == "E6"


def test_to_tool_error_still_falls_back_to_internal_for_unrelated_errors(
    monkeypatch,
):
    monkeypatch.setitem(sys.modules, "app.chat_workspace", None)
    payload = to_tool_error(RuntimeError("boom"))
    assert payload["error"]["code"] == "INTERNAL"


# ---------------------------------------------------------------------------
# Semantic contract: the pinned interface the tool layer implements against.
# ---------------------------------------------------------------------------


def test_semantic_contract_block_is_present_in_chat_errors():
    source = inspect.getsource(app.chat_errors)
    assert 'ATTRIBUTION_MODE="enforce" (E6 BIND_REQUIRED)' in source
    assert "ONLY exempt tool is ``host_workspace_bind``" in source
    assert "app.chat_identity.is_enforcing()" in source
