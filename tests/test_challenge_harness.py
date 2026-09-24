"""Unit tests for automated CTF challenge harness and auto_download_ctf_challenge tool."""

from pathlib import Path
import pytest

from app.ctf.challenge_harness import setup_ctf_harness
from app.tools.ctf_suite import auto_download_ctf_challenge


def test_setup_ctf_harness_scaffolding(tmp_path):
    ws = tmp_path / "chal_workspace"
    res = setup_ctf_harness(
        workspace_dir=ws,
        name="babybof",
        category="pwn",
        target="10.10.10.1:1337",
        description="A simple stack buffer overflow challenge.",
    )

    assert res["ok"] is True
    assert res["name"] == "babybof"
    assert res["category"] == "pwn"

    # Check 3-folder layout
    assert (ws / "challenge").is_dir()
    assert (ws / "script").is_dir()
    assert (ws / "script" / "probes").is_dir()
    assert (ws / "solver").is_dir()

    # Check generated files
    assert (ws / "metadata.json").is_file()
    assert (ws / "challenge" / "NOTE.md").is_file()
    assert (ws / "script" / "analysis.md").is_file()
    assert (ws / "solver" / "solve.py").is_file()
    assert (ws / "solver" / "requirements.txt").is_file()

    # Check solve.py content for pwn template
    solve_content = (ws / "solver" / "solve.py").read_text(encoding="utf-8")
    assert "from pwn import *" in solve_content
    assert "10.10.10.1" in solve_content
    assert "1337" in solve_content

    # Check analysis.md content for candidate flags table
    analysis_content = (ws / "script" / "analysis.md").read_text(encoding="utf-8")
    assert "Candidate Flags Lifecycle" in analysis_content
    assert "CANDIDATE" in analysis_content


def test_auto_download_ctf_challenge_tool(tmp_path, monkeypatch):
    import app.config
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", tmp_path)

    res = auto_download_ctf_challenge(
        name="rsa_easy",
        category="crypto",
        description="Find p and q from n and e.",
    )

    assert res["ok"] is True
    assert res["category"] == "crypto"
    chal_dir = Path(res["workspace_dir"])
    assert (chal_dir / "challenge" / "NOTE.md").is_file()

    assert (chal_dir / "solver" / "solve.py").is_file()
    solve_content = (chal_dir / "solver" / "solve.py").read_text(encoding="utf-8")
    assert "cryptographic solver" in solve_content.lower()


def test_setup_ctf_harness_idempotent_on_resume(tmp_path):
    ws = tmp_path / "resume_workspace"
    setup_ctf_harness(workspace_dir=ws, name="my_task", category="web")

    solve_file = ws / "solver" / "solve.py"
    assert solve_file.is_file()
    custom_script = "#!/usr/bin/env python3\n# CUSTOM USER EXPLOIT"
    solve_file.write_text(custom_script, encoding="utf-8")

    # Resume / re-run harness setup
    setup_ctf_harness(workspace_dir=ws, name="my_task", category="web")

    # Ensure custom script preserved
    assert solve_file.read_text(encoding="utf-8") == custom_script


@pytest.mark.anyio
async def test_host_workspace_bind_enforces_harness_unconditionally(tmp_path, monkeypatch):
    import app.config
    from app.tools.workspace_tools import host_workspace_bind

    monkeypatch.setattr(app.config, "HOST_CHAT_WORKSPACES", True, raising=False)
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", tmp_path, raising=False)
    monkeypatch.setattr(app.config, "HOST_CHAT_ROOT", tmp_path, raising=False)

    # Bind with generic non-CTF label
    res = await host_workspace_bind(label="daily_ops_investigation")
    assert res["ok"] is True
    assert res.get("harness_enforced") is True

    ws_path = Path(res["workspace"])
    assert (ws_path / "challenge").is_dir()
    assert (ws_path / "challenge" / "NOTE.md").is_file()
    assert (ws_path / "script").is_dir()
    assert (ws_path / "script" / "analysis.md").is_file()
    assert (ws_path / "solver").is_dir()
    assert (ws_path / "solver" / "solve.py").is_file()

