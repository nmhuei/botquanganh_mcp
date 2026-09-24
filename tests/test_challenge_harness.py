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


def test_auto_solver_promotion_and_flag_hoarding_pipeline(tmp_path):
    from app.ctf.auto_solver import promote_script_to_solver
    from app.ctf.challenge_harness import setup_ctf_harness

    ws = tmp_path / "pwn_babybof"
    setup_ctf_harness(ws, name="babybof", category="pwn")

    # 1. Create exploit in script/ folder
    script_file = ws / "script" / "exploit.py"
    script_code = """#!/usr/bin/env python3
import requests
from pwn import *

print("Target pwned successfully!")
print("Here is your flag: FLAG{pwn_auto_solver_promoted_vjp_1337}")
"""
    script_file.write_text(script_code, encoding="utf-8")

    # 2. Trigger auto promotion
    stdout_sim = "Target pwned successfully!\nHere is your flag: FLAG{pwn_auto_solver_promoted_vjp_1337}\n"
    res = promote_script_to_solver(
        workspace_root=ws,
        command="python3 script/exploit.py",
        stdout=stdout_sim,
        exit_code=0,
    )

    assert res["promoted"] is True
    assert "FLAG{pwn_auto_solver_promoted_vjp_1337}" in res["flags"]

    # 3. Verify solve.py promoted
    solve_file = ws / "solver" / "solve.py"
    assert solve_file.is_file()
    assert solve_file.read_text(encoding="utf-8") == script_code

    # 4. Verify flag.txt created in root workspace folder
    flag_file = ws / "flag.txt"
    assert flag_file.is_file()
    assert "FLAG{pwn_auto_solver_promoted_vjp_1337}" in flag_file.read_text(encoding="utf-8")

    # 5. Verify WRITEUP.md generated in solver/
    writeup_file = ws / "solver" / "WRITEUP.md"
    assert writeup_file.is_file()
    writeup_content = writeup_file.read_text(encoding="utf-8")
    assert "# Writeup: babybof" in writeup_content
    assert "VERIFIED SOLVED" in writeup_content
    assert "FLAG{pwn_auto_solver_promoted_vjp_1337}" in writeup_content
    assert "python3 solve.py" in writeup_content

    # 6. Verify requirements.txt auto-updated
    reqs_content = (ws / "solver" / "requirements.txt").read_text(encoding="utf-8")
    assert "pwntools" in reqs_content
    assert "requests" in reqs_content


@pytest.mark.anyio
async def test_workspace_bind_reuses_canonical_folder_without_clutter(tmp_path, monkeypatch):
    import app.config
    from app.tools.workspace_tools import host_workspace_bind

    monkeypatch.setattr(app.config, "HOST_CHAT_WORKSPACES", True, raising=False)
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", tmp_path, raising=False)
    monkeypatch.setattr(app.config, "HOST_CHAT_ROOT", tmp_path, raising=False)

    # 1. First bind
    res1 = await host_workspace_bind(label="pwn_babybof")
    assert res1["ok"] is True
    path1 = res1["workspace"]

    # 2. Subsequent binds continue in exact same folder without _v2/_v3 suffixes
    res2 = await host_workspace_bind(label="pwn_babybof")
    assert res2["ok"] is True
    assert res2["workspace"] == path1

    # Verify no _v2 folders were created
    all_dirs = [p.name for p in tmp_path.iterdir() if p.is_dir()]
    assert "pwn_babybof" in all_dirs
    assert not any("_v" in d for d in all_dirs)


@pytest.mark.anyio
async def test_root_protection_and_chat_workspace_auto_scoping(tmp_path, monkeypatch):
    import app.config
    from app.tools.workspace_tools import host_workspace_bind
    from app.tools.host import host_write_file, host_read_file

    monkeypatch.setattr(app.config, "HOST_CHAT_WORKSPACES", True, raising=False)
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", tmp_path, raising=False)
    monkeypatch.setattr(app.config, "HOST_CHAT_ROOT", tmp_path, raising=False)

    # 1. Bind session
    res = await host_workspace_bind(label="pwn_babybof")
    chat_id = res["chat_id"]
    ws_dir = tmp_path / chat_id

    # 2. Write file with relative path "script/exploit.py" -> MUST land inside session folder
    write_res = host_write_file(path="script/exploit.py", content="#!/usr/bin/env python3\nprint('poc')", chat_id=chat_id)
    assert write_res["ok"] is True
    assert (ws_dir / "script" / "exploit.py").is_file()
    assert not (tmp_path / "script").exists(), "Lỗi: Thư mục script rác đã bị tạo ở root!"

    # 3. Read file with relative path -> MUST read from session folder
    read_res = host_read_file(path="script/exploit.py", chat_id=chat_id)
    assert read_res["ok"] is True
    assert "print('poc')" in read_res["content"]

    # 4. Attempt to write absolute path into root/script while in session -> MUST redirect to session folder
    bad_root_script = str(tmp_path / "script" / "redirected.py")
    write_res2 = host_write_file(path=bad_root_script, content="print('safe')", chat_id=chat_id)
    assert write_res2["ok"] is True
    assert (ws_dir / "script" / "redirected.py").is_file()
    assert not (tmp_path / "script").exists(), "Lỗi: Thư mục script rác vẫn bị tạo ở root!"

    # 5. Direct attempt to write into root/script or root/challenge WITHOUT session -> MUST be blocked by BIND_REQUIRED
    (tmp_path / ".last_session").unlink(missing_ok=True)
    from app.chat_identity import _CHAT_ID, _REGISTRY, _REGISTRY_LOCK
    _CHAT_ID.set(None)
    with _REGISTRY_LOCK:
        _REGISTRY.clear()

    blocked_script = host_write_file(path=str(tmp_path / "script" / "hacker.py"), content="evil", chat_id=None)
    assert blocked_script["ok"] is False
    assert "BIND_REQUIRED" in str(blocked_script)

    # 6. Direct call to _resolve_scoped_file_path with root reserved dirs -> MUST raise PermissionError
    from app.tools.host import _resolve_scoped_file_path
    with pytest.raises(PermissionError, match="Policy BQA"):
        _resolve_scoped_file_path(path=str(tmp_path / "script" / "evil.py"), chat_id=None, mode="write")

    with pytest.raises(PermissionError, match="Policy BQA"):
        _resolve_scoped_file_path(path=str(tmp_path / "challenge" / "evil.bin"), chat_id=None, mode="write")

    with pytest.raises(PermissionError, match="Policy BQA"):
        _resolve_scoped_file_path(path=str(tmp_path / "solver" / "evil.py"), chat_id=None, mode="write")



