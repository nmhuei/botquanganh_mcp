import shutil
import pytest
from pathlib import Path

from app.tools import autonomous_agent as aa
from app.tools.autonomous_agent import (
    agent_cancel,
    agent_goal_create,
    agent_report,
    agent_status,
    agent_step,
    agent_goal_start,
    agent_toolchain_capabilities,
)
from app.tools.ctf_harness import ctf_harness_init
from ctfharness.scope import remote_target_allowed, normalize_target_host_port


def _workspace(name: str) -> Path:
    path = Path.home() / "Workspace" / name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    return path


def test_agent_goal_create_status_cancel_report(tmp_path, monkeypatch):
    monkeypatch.setattr(aa, "AGENT_GOALS_DIR", tmp_path / "agent_goals")
    workspace = _workspace(".agent_goal_lifecycle")
    try:
        created = agent_goal_create("inspect this workspace", cwd=str(workspace))

        assert created["ok"] is True
        assert created["status"] == "active"
        assert created["budget"]["max_steps"] == 20
        assert (tmp_path / "agent_goals" / created["goal_id"] / "artifacts").is_dir()

        status = agent_status(created["goal_id"])
        assert status["ok"] is True
        assert status["timeline_events"] == 1

        cancelled = agent_cancel(created["goal_id"])
        assert cancelled["status"] == "cancelled"

        report = agent_report(created["goal_id"])
        assert report["ok"] is True
        assert "Agent Goal Report" in report["content"]
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.anyio
async def test_agent_step_risky_objective_needs_approval(tmp_path, monkeypatch):
    monkeypatch.setattr(aa, "AGENT_GOALS_DIR", tmp_path / "agent_goals")
    workspace = _workspace(".agent_goal_risky")
    try:
        from app import event_bus
        import asyncio
        created = agent_goal_create("run sudo apt install package", cwd=str(workspace))
        
        step_task = asyncio.create_task(agent_step(created["goal_id"]))
        await asyncio.sleep(0.1)

        assert event_bus.pending_approval(created["goal_id"]) is True

        event_bus.resolve_approval(created["goal_id"], False)
        stepped = await step_task

        assert stepped["status"] == "needs_approval"
        assert stepped["kind"] == "needs_approval"
        assert stepped["risk_matches"][0]["rule"] == "install_package"
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.anyio
async def test_agent_step_inspects_workspace_and_completes(tmp_path, monkeypatch):
    monkeypatch.setattr(aa, "AGENT_GOALS_DIR", tmp_path / "agent_goals")
    workspace = _workspace(".agent_goal_steps")
    (workspace / "note.txt").write_text("hello", encoding="utf-8")
    try:
        created = agent_goal_create("inspect files", cwd=str(workspace), budget={"max_steps": 5})

        first = await agent_step(created["goal_id"])
        assert first["step"]["kind"] == "cwd_inspected"
        assert any(item["name"] == "note.txt" for item in first["step"]["observation"]["items"])

        second = await agent_step(created["goal_id"])
        assert second["step"]["kind"] == "policy_checked"

        third = await agent_step(created["goal_id"])
        assert third["status"] == "completed"
        assert third["step"]["kind"] == "decision_point"
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.anyio
async def test_agent_step_loads_ctf_instructions_then_checks_harness(tmp_path, monkeypatch):
    monkeypatch.setattr(aa, "AGENT_GOALS_DIR", tmp_path / "agent_goals")
    workspace = _workspace(".agent_goal_ctf")
    try:
        init = ctf_harness_init("agent-ctf", "misc", cwd=str(workspace), force=True)
        assert init["ok"] is True

        created = agent_goal_create("solve this ctf challenge", cwd=str(workspace), budget={"max_steps": 5})
        first = await agent_step(created["goal_id"])
        second = await agent_step(created["goal_id"])

        assert first["step"]["kind"] == "instructions_loaded"
        assert second["step"]["kind"] == "harness_checked"
        assert second["step"]["observation"]["ok"] is True
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.anyio
async def test_agent_pwn_toolchain_runs_recon_and_writes_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(aa, "AGENT_GOALS_DIR", tmp_path / "agent_goals")
    workspace = _workspace(".agent_goal_pwn")
    source = workspace / "chall.c"
    binary = workspace / "chall"
    source.write_text(
        """
        #include <stdio.h>
        #include <unistd.h>
        int main(void) {
            char buf[32];
            puts("name?");
            read(0, buf, 128);
            puts(buf);
            return 0;
        }
        """,
        encoding="utf-8",
    )
    try:
        import subprocess

        subprocess.run(["gcc", "-fno-stack-protector", "-no-pie", "-o", str(binary), str(source)], check=True)
        created = agent_goal_create("pwn exploit chain", cwd=str(workspace), budget={"max_steps": 8})

        first = await agent_step(created["goal_id"])
        second = await agent_step(created["goal_id"])
        third = await agent_step(created["goal_id"])
        fourth = await agent_step(created["goal_id"])
        fifth = await agent_step(created["goal_id"])

        artifact_dir = tmp_path / "agent_goals" / created["goal_id"] / "artifacts"
        assert first["step"]["kind"] == "pwn_tool_status"
        assert second["step"]["kind"] == "pwn_recon"
        assert third["step"]["kind"] == "pwn_gadgets"
        assert fourth["step"]["kind"] == "pwn_libc"
        assert fifth["step"]["kind"] == "pwn_summary"
        assert (artifact_dir / "pwn-file.stdout.txt").exists()
        assert (artifact_dir / "solve_pwn_template.py").exists()
        assert (artifact_dir / "pwn_toolchain_summary.md").exists()
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_agent_toolchain_capabilities_reports_pwn():
    res = agent_toolchain_capabilities()

    assert res["ok"] is True
    assert res["toolchains"]["pwn"]["status"] == "implemented"
    assert "recon" in res["toolchains"]["pwn"]["stages"]
    assert "ptrlib" in res["toolchains"]["pwn"]["catalog"]["core_libraries"]
    assert "AutoPwn" in res["toolchains"]["pwn"]["catalog"]["automated_exploit"]
    assert "ROPium" in res["toolchains"]["pwn"]["catalog"]["rop_construction"]
    assert "Binary Ninja" in res["toolchains"]["pwn"]["catalog"]["debug_re"]
    assert "rop_gadgets" in res["toolchains"]["pwn"]["command_groups"]
    assert res["toolchains"]["web"]["status"] == "implemented_safe_recon"
    assert res["toolchains"]["crypto"]["status"] == "implemented_safe_recon"
    assert res["toolchains"]["forensics"]["status"] == "implemented_safe_recon"
    assert res["toolchains"]["reverse"]["status"] == "implemented_safe_recon"
    assert "evaluation" in res["toolchains"]["web"]
    assert "approval_required" in res["toolchains"]["crypto"]["safety_model"]


@pytest.mark.anyio
async def test_agent_web_toolchain_creates_safe_recon_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(aa, "AGENT_GOALS_DIR", tmp_path / "agent_goals")
    workspace = _workspace(".agent_goal_web")
    try:
        created = agent_goal_create(
            "web challenge https://example.com",
            cwd=str(workspace),
            scope={"allowed_hosts": ["example.com"]},
            budget={"max_steps": 4}
        )
        first = await agent_step(created["goal_id"])
        second = await agent_step(created["goal_id"])

        artifact_dir = tmp_path / "agent_goals" / created["goal_id"] / "artifacts"
        assert first["step"]["kind"] == "web_tool_status"
        assert second["step"]["kind"] == "web_recon"
        assert (artifact_dir / "web_recon_plan.md").exists()
        assert second["step"]["observation"]["urls"] == ["https://example.com"]
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.anyio
async def test_agent_crypto_toolchain_runs_local_recon(tmp_path, monkeypatch):
    monkeypatch.setattr(aa, "AGENT_GOALS_DIR", tmp_path / "agent_goals")
    workspace = _workspace(".agent_goal_crypto")
    (workspace / "cipher.txt").write_text("U1RBUlQ6IGZsYWd7dGVzdH0=", encoding="utf-8")
    try:
        created = agent_goal_create("crypto challenge", cwd=str(workspace), budget={"max_steps": 4})
        first = await agent_step(created["goal_id"])
        second = await agent_step(created["goal_id"])

        assert first["step"]["kind"] == "crypto_tool_status"
        assert second["step"]["kind"] == "crypto_recon"
        assert second["step"]["observation"]["candidate_files"][0]["relative_path"] == "cipher.txt"
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.anyio
async def test_agent_forensics_toolchain_runs_local_recon(tmp_path, monkeypatch):
    monkeypatch.setattr(aa, "AGENT_GOALS_DIR", tmp_path / "agent_goals")
    workspace = _workspace(".agent_goal_forensics")
    (workspace / "evidence.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    try:
        created = agent_goal_create("forensics challenge", cwd=str(workspace), budget={"max_steps": 4})
        first = await agent_step(created["goal_id"])
        second = await agent_step(created["goal_id"])

        assert first["step"]["kind"] == "forensics_tool_status"
        assert second["step"]["kind"] == "forensics_recon"
        assert second["step"]["observation"]["candidate_files"][0]["relative_path"] == "evidence.png"
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.anyio
async def test_agent_reverse_toolchain_prefers_binary_recon(tmp_path, monkeypatch):
    monkeypatch.setattr(aa, "AGENT_GOALS_DIR", tmp_path / "agent_goals")
    workspace = _workspace(".agent_goal_reverse")
    source = workspace / "rev.c"
    binary = workspace / "rev"
    source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
    try:
        import subprocess

        subprocess.run(["gcc", "-o", str(binary), str(source)], check=True)
        created = agent_goal_create("reverse challenge", cwd=str(workspace), budget={"max_steps": 4})
        first = await agent_step(created["goal_id"])
        second = await agent_step(created["goal_id"])

        assert first["step"]["kind"] == "reverse_tool_status"
        assert second["step"]["kind"] == "reverse_recon"
        assert second["step"]["observation"]["candidate_files"][0]["relative_path"] == "rev"
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.anyio
async def test_agent_goal_start_continuous_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(aa, "AGENT_GOALS_DIR", tmp_path / "agent_goals")
    workspace = _workspace(".agent_goal_continuous")
    (workspace / "note.txt").write_text("hello", encoding="utf-8")
    try:
        created = agent_goal_create("inspect files", cwd=str(workspace), budget={"max_steps": 5})
        res = await agent_goal_start(created["goal_id"], mode="bounded_auto")

        assert res["status"] == "completed"
        assert res["steps_taken"] >= 3
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_target_normalization_and_scope():
    # Test normalization cases
    assert normalize_target_host_port("http://target.ctf:8080") == [("target.ctf", 8080)]
    assert normalize_target_host_port("target.ctf:8080") == [("target.ctf", 8080)]
    assert normalize_target_host_port("nc target.ctf 8080") == [("target.ctf", 8080)]
    assert normalize_target_host_port("target.ctf") == [("target.ctf", None)]

    # Test scope verification cases
    allowed_domains = ["*.ctf.example.com", "target.ctf:8080", "safe-host"]
    
    # Matching wildcard domain
    ok, msg = remote_target_allowed("http://chall.ctf.example.com:9000", allowed_domains)
    assert ok is True

    # Matching exact domain and port
    ok, msg = remote_target_allowed("target.ctf:8080", allowed_domains)
    assert ok is True

    # Mismatching port
    ok, msg = remote_target_allowed("target.ctf:9090", allowed_domains)
    assert ok is False

    # Blocked domain
    ok, msg = remote_target_allowed("malicious.com", allowed_domains)
    assert ok is False


@pytest.mark.anyio
async def test_agent_approve_and_reject_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(aa, "AGENT_GOALS_DIR", tmp_path / "agent_goals")
    workspace = _workspace(".agent_goal_approve_reject")
    try:
        from app import event_bus
        from app.tools.autonomous_agent import agent_approve, agent_reject
        import asyncio

        # Create a risky goal
        created = agent_goal_create("run sudo apt install package", cwd=str(workspace))
        goal_id = created["goal_id"]

        # Subscribe to simulate active SSE/WS client
        q = event_bus.subscribe(goal_id)

        # Run step in background since it will block waiting for approval
        step_task = asyncio.create_task(agent_step(goal_id))
        await asyncio.sleep(0.1)

        assert event_bus.pending_approval(goal_id) is True

        # Call agent_approve
        app_res = agent_approve(goal_id)
        assert app_res["ok"] is True
        assert event_bus.pending_approval(goal_id) is False

        # Wait for the step task to finish
        stepped = await step_task
        assert stepped["status"] == "active"
        # Since it succeeded, the step continued to run cwd_inspected
        assert stepped["step"]["kind"] == "cwd_inspected"

        # Now run another step, which should run the actual command check
        stepped_after = await agent_step(goal_id, approval="approved")
        assert stepped_after["step"]["kind"] == "policy_checked"
        
        event_bus.unsubscribe(goal_id, q)

        # Test agent_reject
        created2 = agent_goal_create("run sudo apt install package", cwd=str(workspace))
        goal_id2 = created2["goal_id"]
        
        q2 = event_bus.subscribe(goal_id2)
        step_task2 = asyncio.create_task(agent_step(goal_id2))
        await asyncio.sleep(0.1)

        assert event_bus.pending_approval(goal_id2) is True
        
        # Call agent_reject
        rej_res = agent_reject(goal_id2)
        assert rej_res["ok"] is True
        assert rej_res["status"] == "cancelled"
        assert event_bus.pending_approval(goal_id2) is False

        stepped2 = await step_task2
        assert stepped2["message"] == "Approval rejected by client."
        
        # Verify the status is cancelled on disk
        status2 = agent_status(goal_id2)
        assert status2["status"] == "cancelled"
        
        event_bus.unsubscribe(goal_id2, q2)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

