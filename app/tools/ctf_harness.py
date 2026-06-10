from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.agent_paths import resolve_agent_path
from app.config import BASE_DIR, MAX_OUTPUT_BYTES
from app.logging_audit import log_audit_event
from app.mcp_server import mcp
from app.security import format_error_response


CTFH_SUPPORTED_CATEGORIES = [
    "web",
    "pwn",
    "rev",
    "reverse",
    "crypto",
    "forensics",
    "misc",
    "osint",
    "ai-ml",
    "cloud-ci",
]


def _python_bin() -> str:
    venv_python = BASE_DIR / ".venv" / "bin" / "python"
    return str(venv_python if venv_python.exists() else sys.executable)


def _resolve_cwd(cwd: str | None) -> Path:
    if not cwd:
        return BASE_DIR
    path = resolve_agent_path(cwd)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _truncate(text: str, limit: int | None = None) -> str:
    limit = limit or min(MAX_OUTPUT_BYTES, 80_000)
    if len(text.encode("utf-8", errors="replace")) <= limit:
        return text
    encoded = text.encode("utf-8", errors="replace")[:limit]
    return encoded.decode("utf-8", errors="replace") + "\n...[truncated]"


def _read_gpt_md(max_chars: int | None = None) -> dict:
    path = BASE_DIR / "GPT.md"
    if not path.exists():
        raise FileNotFoundError(f"Missing harness instruction file: {path}")
    content = path.read_text(encoding="utf-8", errors="replace")
    return {
        "path": str(path),
        "content": _truncate(content, max_chars or 40_000),
        "truncated": len(content) > (max_chars or 40_000),
    }


def _run_ctfh(args: list[str], cwd: Path, timeout_seconds: int) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BASE_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    command = [_python_bin(), "-m", "ctfharness.cli", *args]
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_seconds,
        check=False,
    )
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "command": " ".join(command),
        "cwd": str(cwd),
        "stdout": _truncate(proc.stdout),
        "stderr": _truncate(proc.stderr),
    }


@mcp.tool(
    name="ctf_harness_capabilities",
    description="Returns the local CTF harness categories, commands, templates, skills, and integration paths.",
)
def ctf_harness_capabilities() -> dict:
    try:
        templates_dir = BASE_DIR / "templates"
        skills_dir = BASE_DIR / "skills"
        categories = [p.name for p in templates_dir.iterdir() if p.is_dir()] if templates_dir.exists() else []
        skills = [p.name for p in skills_dir.iterdir() if (p / "SKILL.md").exists()] if skills_dir.exists() else []
        return {
            "ok": True,
            "service": "ctf-harness",
            "version": "0.3.0",
            "commands": ["init", "check", "local", "solve", "remote", "verify", "workspace", "report", "pack"],
            "supported_categories": CTFH_SUPPORTED_CATEGORIES,
            "template_categories": sorted(categories),
            "skills": sorted(skills),
            "bootstrap": {
                "required_first_tool": "ctf_harness_instructions",
                "instruction_file": str(BASE_DIR / "GPT.md"),
                "reason": "Read this before CTF work so ChatGPT follows the harness pipeline, guardrails, and verification rules.",
            },
            "paths": {
                "package": str(BASE_DIR / "ctfharness"),
                "templates": str(templates_dir),
                "skills": str(skills_dir),
                "example_config": str(BASE_DIR / "ctf.example.yaml"),
            },
            "usage": {
                "init": "ctf_harness_init(name, category, cwd, host='', port='')",
                "check": "ctf_harness_check(config='ctf.yaml', cwd='...')",
                "solve_local": "ctf_harness_solve(config='ctf.yaml', mode='local', cwd='...')",
                "verify": "ctf_harness_verify(config='ctf.yaml', mode='local|remote', cwd='...')",
            },
        }
    except Exception as e:
        log_audit_event("CTF_HARNESS_CAPABILITIES_FAIL", {"error": str(e)})
        return format_error_response(e)


@mcp.tool(
    name="ctf_harness_instructions",
    description="Read GPT.md, the required CTF harness operating instructions ChatGPT should load before solving a challenge.",
)
def ctf_harness_instructions(max_chars: int = 40000) -> dict:
    try:
        data = _read_gpt_md(max_chars=max_chars)
        log_audit_event("CTF_HARNESS_INSTRUCTIONS", {"path": data["path"], "truncated": data["truncated"]})
        return {
            "ok": True,
            "summary": (
                "Required CTF harness instructions loaded. Follow TRIAGE -> RECON -> "
                "HYPOTHESIS -> EXPLOIT -> VERIFY -> REPORT; keep changes simple and "
                "surgical; never claim a flag without working exploit/evidence."
            ),
            **data,
        }
    except Exception as e:
        log_audit_event("CTF_HARNESS_INSTRUCTIONS_FAIL", {"error": str(e)})
        return format_error_response(e)


@mcp.tool(
    name="ctf_harness_init",
    description="Initializes a CTF harness workspace and ctf.yaml in the selected working directory.",
)
def ctf_harness_init(
    name: str,
    category: str = "misc",
    cwd: str = "",
    host: str = "",
    port: str = "",
    force: bool = False,
    timeout_seconds: int = 30,
) -> dict:
    try:
        if category not in CTFH_SUPPORTED_CATEGORIES:
            raise ValueError(f"unsupported category: {category}")
        args = ["init", "--name", name, "--category", category]
        if host:
            args.extend(["--host", host])
        if port:
            args.extend(["--port", str(port)])
        if force:
            args.append("--force")
        result = _run_ctfh(args, _resolve_cwd(cwd), timeout_seconds)
        log_audit_event("CTF_HARNESS_INIT", {"name": name, "category": category, "ok": result["ok"]})
        return result
    except Exception as e:
        log_audit_event("CTF_HARNESS_INIT_FAIL", {"name": name, "error": str(e)})
        return format_error_response(e)


@mcp.tool(name="ctf_harness_check", description="Validates a CTF harness config and creates workspace folders.")
def ctf_harness_check(config: str = "ctf.yaml", cwd: str = "", timeout_seconds: int = 30) -> dict:
    try:
        result = _run_ctfh(["--config", config, "check"], _resolve_cwd(cwd), timeout_seconds)
        log_audit_event("CTF_HARNESS_CHECK", {"config": config, "ok": result["ok"]})
        return result
    except Exception as e:
        log_audit_event("CTF_HARNESS_CHECK_FAIL", {"config": config, "error": str(e)})
        return format_error_response(e)


@mcp.tool(
    name="ctf_harness_local",
    description="Runs the harness local build/start/smoke pipeline and optionally the local solver.",
)
def ctf_harness_local(
    config: str = "ctf.yaml",
    cwd: str = "",
    solve: bool = False,
    keep_local: bool = False,
    timeout_seconds: int = 120,
) -> dict:
    try:
        args = ["--config", config, "local"]
        if solve:
            args.append("--solve")
        if keep_local:
            args.append("--keep-local")
        args.extend(["--timeout", str(timeout_seconds)])
        result = _run_ctfh(args, _resolve_cwd(cwd), timeout_seconds + 10)
        log_audit_event("CTF_HARNESS_LOCAL", {"config": config, "solve": solve, "ok": result["ok"]})
        return result
    except Exception as e:
        log_audit_event("CTF_HARNESS_LOCAL_FAIL", {"config": config, "error": str(e)})
        return format_error_response(e)


@mcp.tool(name="ctf_harness_solve", description="Runs the local or remote solver from ctf.yaml.")
def ctf_harness_solve(
    config: str = "ctf.yaml",
    mode: str = "local",
    cwd: str = "",
    force_remote: bool = False,
    timeout_seconds: int = 120,
) -> dict:
    try:
        if mode not in {"local", "remote"}:
            raise ValueError("mode must be 'local' or 'remote'")
        args = ["--config", config, "solve", "--mode", mode, "--timeout", str(timeout_seconds)]
        if force_remote:
            args.append("--force-remote")
        result = _run_ctfh(args, _resolve_cwd(cwd), timeout_seconds + 10)
        log_audit_event("CTF_HARNESS_SOLVE", {"config": config, "mode": mode, "ok": result["ok"]})
        return result
    except Exception as e:
        log_audit_event("CTF_HARNESS_SOLVE_FAIL", {"config": config, "mode": mode, "error": str(e)})
        return format_error_response(e)


@mcp.tool(name="ctf_harness_verify", description="Scans harness artifacts/logs for flag candidates and writes evidence JSON.")
def ctf_harness_verify(config: str = "ctf.yaml", mode: str = "local", cwd: str = "", timeout_seconds: int = 60) -> dict:
    try:
        if mode not in {"local", "remote"}:
            raise ValueError("mode must be 'local' or 'remote'")
        result = _run_ctfh(["--config", config, "verify", "--mode", mode], _resolve_cwd(cwd), timeout_seconds)
        log_audit_event("CTF_HARNESS_VERIFY", {"config": config, "mode": mode, "ok": result["ok"]})
        return result
    except Exception as e:
        log_audit_event("CTF_HARNESS_VERIFY_FAIL", {"config": config, "mode": mode, "error": str(e)})
        return format_error_response(e)


@mcp.tool(name="ctf_harness_report", description="Generates a Markdown report from harness logs and proof files.")
def ctf_harness_report(config: str = "ctf.yaml", cwd: str = "", timeout_seconds: int = 60) -> dict:
    try:
        result = _run_ctfh(["--config", config, "report"], _resolve_cwd(cwd), timeout_seconds)
        log_audit_event("CTF_HARNESS_REPORT", {"config": config, "ok": result["ok"]})
        return result
    except Exception as e:
        log_audit_event("CTF_HARNESS_REPORT_FAIL", {"config": config, "error": str(e)})
        return format_error_response(e)


@mcp.tool(name="ctf_harness_pack", description="Zips harness challenge artifacts for sharing or archival.")
def ctf_harness_pack(config: str = "ctf.yaml", cwd: str = "", timeout_seconds: int = 60) -> dict:
    try:
        result = _run_ctfh(["--config", config, "pack"], _resolve_cwd(cwd), timeout_seconds)
        log_audit_event("CTF_HARNESS_PACK", {"config": config, "ok": result["ok"]})
        return result
    except Exception as e:
        log_audit_event("CTF_HARNESS_PACK_FAIL", {"config": config, "error": str(e)})
        return format_error_response(e)
