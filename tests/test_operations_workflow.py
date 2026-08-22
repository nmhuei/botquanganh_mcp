import json
import os
from pathlib import Path
from types import SimpleNamespace


from app.cli.commands import doctor as doctor_module
from app.cli.commands.config import handle_config
from app.cli.config_view import DEFAULTS, validate_config
from app.cli.context import CLIContext
from app.cli.parser import build_parser


def _make_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


def test_parser_supports_strict_and_local_only_modes():
    parser = build_parser()
    doctor = parser.parse_args(["doctor", "--strict", "--local-only"])
    assert doctor.strict is True
    assert doctor.local_only is True
    config = parser.parse_args(["config", "validate", "--strict"])
    assert config.strict is True


def test_config_validation_covers_capacity_permissions_and_process_identity(
    tmp_path, monkeypatch
):
    repo = tmp_path / "repo"
    repo.mkdir()
    workspace = repo / "workspace"
    workspace.mkdir()
    knowledge = repo / "knowledge"
    knowledge.mkdir()
    (knowledge / "TOOL_CATALOG.json").write_text("[]", encoding="utf-8")
    env_file = repo / ".env"
    env_file.write_text("GATEWAY_TOKEN=secret\n", encoding="utf-8")
    env_file.chmod(0o644)
    for relative in (
        ".venv/bin/fastmcp",
        "bin/bqa",
        "scripts/process_helpers.sh",
    ):
        _make_executable(repo / relative)

    values = {
        **DEFAULTS,
        "HOST_WORKSPACE_DIR": str(workspace),
        "HOST_KNOWLEDGE_DIR": str(knowledge),
        "GATEWAY_TOKEN": "secret",
        "REQUIRE_AUTH": "true",
        "MAX_CONCURRENT_COMMANDS": "0",
        "LOG_FILE": str(repo / "logs" / "gateway.log"),
    }
    monkeypatch.setattr("shutil.which", lambda name: None)
    checks = {item["name"]: item for item in validate_config(repo, values)}
    assert checks["env_permissions"]["status"] == "fail"
    assert checks["config_max_concurrent_commands"]["status"] == "fail"
    assert checks["tool_catalog"]["status"] == "pass"

    env_file.chmod(0o600)
    values["MAX_CONCURRENT_COMMANDS"] = "4"
    checks = {item["name"]: item for item in validate_config(repo, values)}
    assert checks["env_permissions"]["status"] == "pass"
    assert checks["config_max_concurrent_commands"]["status"] == "pass"


def test_config_strict_mode_fails_on_warning(tmp_path, capsys):
    repo = tmp_path
    ctx = CLIContext(
        repo_root=repo,
        values={},
        base_url="http://127.0.0.1:1",
        token="",
        request_timeout=1,
        json_output=True,
    )
    args = SimpleNamespace(config_command="validate", strict=True)
    # Empty isolated repo creates failures; the strict contract still reports counts.
    assert handle_config(ctx, args) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["strict"] is True
    assert payload["ok"] is False
    assert payload["failure_count"] >= 1


def test_doctor_local_only_skips_public_and_strict_counts_warnings(
    tmp_path, monkeypatch, capsys
):
    for relative in (
        ".venv/bin/python",
        ".venv/bin/fastmcp",
        "bin/bqa",
        "scripts/process_helpers.sh",
        "scripts/quality_gate.sh",
    ):
        _make_executable(tmp_path / relative)
    (tmp_path / "logs").mkdir()

    ctx = CLIContext(
        repo_root=tmp_path,
        values={
            **DEFAULTS,
            "HOST_WORKSPACE_DIR": str(tmp_path),
            "HOST_KNOWLEDGE_DIR": str(tmp_path),
            "LOG_FILE": str(tmp_path / "logs" / "gateway.log"),
            "REQUIRE_AUTH": "false",
        },
        base_url="http://127.0.0.1:1",
        token="",
        request_timeout=1,
        json_output=True,
    )
    runtime = {
        "ok": True,
        "supervisor": {"running": True, "pid": 1},
        "server": {"running": True, "pid": 2},
        "tunnel": {"running": True, "pid": 3},
        "bridge": "ready",
        "url": "https://example.trycloudflare.com/mcp",
        "auth_required": False,
        "workspace": str(tmp_path),
    }
    monkeypatch.setattr(doctor_module, "status_data", lambda *_args: runtime)
    monkeypatch.setattr(
        doctor_module,
        "validate_config",
        lambda *_args: [{"name": "authentication", "status": "warn", "message": "disabled"}],
    )
    monkeypatch.setattr(
        doctor_module,
        "_request_check",
        lambda _client, _path, name, **_kwargs: {"name": name, "status": "pass", "message": "ok"},
    )
    monkeypatch.setattr(
        doctor_module,
        "_mcp_check",
        lambda _client, _path, name: {"name": name, "status": "pass", "message": "ok"},
    )
    monkeypatch.setattr(doctor_module, "_package_check", lambda: {"name": "editable_package", "status": "pass", "message": "1.0.0"})
    monkeypatch.setattr(doctor_module.shutil, "which", lambda name: str(tmp_path / "bin" / "bqa") if name == "bqa" else "/bin/true")

    args = SimpleNamespace(strict=True, local_only=True)
    assert doctor_module.handle_doctor(ctx, args) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["strict"] is True
    assert payload["local_only"] is True
    assert payload["warning_count"] >= 1
    assert not any(item["name"].startswith("public_") for item in payload["checks"])


def test_quality_gate_and_diagnostics_scripts_are_executable():
    repo = Path(__file__).resolve().parents[1]
    for relative in ("scripts/quality_gate.sh", "scripts/collect_diagnostics.sh"):
        path = repo / relative
        assert path.is_file()
        assert os.access(path, os.X_OK)
    assert "quality_gate.sh" in (repo / "scripts" / "test.sh").read_text(encoding="utf-8")
