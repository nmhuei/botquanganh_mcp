import json
import time

import pytest

import app.config
from app.host.executor import execute_host_command


@pytest.fixture
def command_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(app.config, "HOST_RESTRICT_TO_WORKSPACE", True)
    monkeypatch.setattr(app.config, "HOST_COMMAND_POLICY", "guarded")
    monkeypatch.setattr(app.config, "HOST_INHERIT_ENV", True)
    monkeypatch.setattr(app.config, "HOST_ENV_ALLOWLIST", [])
    monkeypatch.setattr(app.config, "MAX_OUTPUT_BYTES", 10_000)
    monkeypatch.setattr(app.config, "MAX_TIMEOUT_SECONDS", 10)
    return tmp_path


def test_inherited_environment_preserves_secrets(command_workspace, monkeypatch):
    monkeypatch.setenv("GATEWAY_TOKEN", "gateway-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "api-secret")
    monkeypatch.setenv("SAFE_VALUE", "safe")
    monkeypatch.setenv("CUSTOM_TOKEN", "allowed-secret")
    monkeypatch.setattr(app.config, "HOST_ENV_ALLOWLIST", ["CUSTOM_TOKEN"])

    command = (
        "python3 -c \"import json,os; "
        "print(json.dumps({k: os.environ.get(k) for k in "
        "['GATEWAY_TOKEN','OPENAI_API_KEY','SAFE_VALUE','CUSTOM_TOKEN']}))\""
    )
    result = execute_host_command(command, timeout_seconds=5)
    payload = json.loads(result["stdout"])
    assert payload == {
        "GATEWAY_TOKEN": "gateway-secret",
        "OPENAI_API_KEY": "api-secret",
        "SAFE_VALUE": "safe",
        "CUSTOM_TOKEN": "allowed-secret",
    }


def test_shell_startup_injection_environment_is_removed(command_workspace, monkeypatch):
    hook = command_workspace / "bash-env.sh"
    marker = command_workspace / "injected.txt"
    hook.write_text(f"printf injected > {marker}\n", encoding="utf-8")
    monkeypatch.setenv("BASH_ENV", str(hook))

    result = execute_host_command("printf clean", timeout_seconds=5)
    assert result["stdout"] == "clean"
    assert not marker.exists()


def test_stdout_and_stderr_are_bounded_while_draining(command_workspace, monkeypatch):
    monkeypatch.setattr(app.config, "MAX_OUTPUT_BYTES", 1024)
    command = (
        "python3 -c \"import sys; "
        "sys.stdout.write('o'*2000000); sys.stdout.flush(); "
        "sys.stderr.write('e'*2000000); sys.stderr.flush()\""
    )
    result = execute_host_command(command, timeout_seconds=8)
    assert result["ok"] is True
    assert result["stdout_truncated"] is True
    assert result["stderr_truncated"] is True
    assert result["stdout"].startswith("o" * 100)
    assert result["stderr"].startswith("e" * 100)
    assert len(result["stdout"].encode()) < 1200
    assert len(result["stderr"].encode()) < 1200


def test_zero_output_limit_keeps_complete_streams(command_workspace, monkeypatch):
    """The documented zero setting means unlimited capture, not no capture."""
    monkeypatch.setattr(app.config, "MAX_OUTPUT_BYTES", 0)

    result = execute_host_command(
        "python3 -c \"import sys; print('release stdout'); print('release stderr', file=sys.stderr)\"",
        timeout_seconds=5,
    )

    assert result["ok"] is True
    assert result["stdout"] == "release stdout\n"
    assert result["stderr"] == "release stderr\n"
    assert result["stdout_truncated"] is False
    assert result["stderr_truncated"] is False


def test_timeout_terminates_background_child_group(command_workspace):
    command = (
        "python3 -c \"import subprocess,time; "
        "subprocess.Popen(['bash','-c','sleep 2; printf survived > child.txt']); "
        "time.sleep(10)\""
    )
    result = execute_host_command(command, timeout_seconds=1)
    assert result["ok"] is False
    assert result["error"]["code"] == "TIMEOUT"
    time.sleep(2.2)
    assert not (command_workspace / "child.txt").exists()
