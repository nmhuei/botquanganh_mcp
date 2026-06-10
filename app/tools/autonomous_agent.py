from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from app.agent_paths import resolve_agent_path
from app.config import BASE_DIR
from app.logging_audit import log_audit_event
from app.mcp_server import mcp
from app.security import format_error_response
from app.tools.ctf_harness import ctf_harness_check, ctf_harness_instructions
from app.tools.shell import policy_check_command


AGENT_GOALS_DIR = BASE_DIR / "logs" / "agent_goals"
DEFAULT_MAX_STEPS = 20
DEFAULT_MAX_SECONDS = 900
MAX_TOOLCHAIN_OUTPUT = 120_000

PWN_COMMAND_GROUPS = {
    "core_system": ["python3", "file", "strings", "readelf", "objdump", "nm", "checksec"],
    "debug_trace": ["gdb", "strace", "ltrace"],
    "rop_gadgets": ["ROPgadget", "ropper", "rp++", "one_gadget"],
    "elf_libc_helpers": ["patchelf", "pwninit", "ldd"],
    "re_cli": ["rizin", "radare2", "r2", "rz-bin", "ghidraRun", "cutter", "ida64", "binaryninja"],
    "shellcode_payload": ["msfvenom"],
    "autopwn_frameworks": ["zeratool", "pwnpasi", "autopwn", "liveexploit", "bloodfang", "koshary"],
}

PWN_PYTHON_MODULES = ["pwn", "ptrlib", "angr", "qiling", "triton", "manticore", "LibcSearcher"]

PWN_TOOLCHAIN_CATALOG = {
    "core_libraries": ["pwntools", "ptrlib", "ronin-exploits"],
    "automated_exploit": ["pwnpasi", "AutoPwn", "LiveExploit", "BloodFang", "Koshary", "Zeratool", "angr/rex"],
    "rop_construction": ["ROPgadget", "angrop", "ropper", "rp++", "ROPium", "Exrop"],
    "debug_re": ["gdb", "pwndbg", "gef", "peda", "Ghidra", "CutterMCP+", "IDA Pro", "Binary Ninja"],
    "helpers": ["one_gadget", "patchelf", "pwninit", "LibcSearcher", "Loopwn", "msfvenom", "pwntools.shellcraft"],
}

WEB_COMMAND_GROUPS = {
    "http_basics": ["curl", "wget", "httpx", "httpie"],
    "fingerprint": ["whatweb", "wappalyzer", "webanalyze", "gowitness", "eyewitness"],
    "content_discovery": ["ffuf", "feroxbuster", "gobuster", "dirb", "dirsearch"],
    "params": ["arjun", "paramspider", "x8"],
    "vuln_scanners": ["nuclei", "sqlmap", "xsstrike", "commix", "tplmap", "ssrfmap", "jaeles"],
    "recon": ["nmap", "subfinder", "amass", "assetfinder", "massdns", "reconftw"],
    "browser": ["playwright", "selenium", "chromium", "google-chrome"],
}

WEB_PYTHON_MODULES = ["requests", "bs4", "lxml", "playwright", "selenium", "httpx"]

WEB_TOOLCHAIN_CATALOG = {
    "recon_fingerprint": ["Neo-Recon", "GhostTagger", "whatweb", "Wappalyzer CLI", "webanalyze"],
    "discovery": ["ffuf", "gobuster", "dirb", "dirsearch", "feroxbuster"],
    "params_vulns": ["Arjun", "ParamSpider", "x8", "SQLMap", "XSStrike", "Commix", "Tplmap", "SSRFmap"],
    "scanning": ["Nmap", "nuclei", "Jaeles", "AutoRecon", "ReconFTW"],
    "manual_dynamic": ["Burp Suite", "Turbo Intruder", "Playwright", "Selenium"],
}

CRYPTO_COMMAND_GROUPS = {
    "math_runtime": ["sage", "python3", "openssl", "bc", "pari-gp"],
    "solvers": ["z3", "RsaCtfTool", "rsatool", "ciphey", "katana"],
    "hash_password": ["hashcat", "john"],
    "classical": ["quipqiup", "featherduster"],
    "oracle_attacks": ["padbuster", "poracle", "hash_extender"],
    "encoding": ["base64", "xxd", "hexdump", "CyberChef"],
}

CRYPTO_PYTHON_MODULES = ["Crypto", "z3", "sageall", "sympy", "gmpy2", "numpy"]

CRYPTO_TOOLCHAIN_CATALOG = {
    "rsa_number_theory": ["RsaCtfTool", "X-RSA", "SageMath", "gmpy2", "sympy"],
    "smt_symbolic": ["Z3", "SageMath"],
    "encoding_classical": ["CyberChef", "Ciphey", "Katana", "dCode/dcodr", "Boxentriq", "quipqiup"],
    "hash_oracle": ["hashcat", "john", "PadBuster", "POET", "hash_extender"],
    "llm_assist": ["KryptoPilot", "FeatherDuster"],
}

FORENSICS_COMMAND_GROUPS = {
    "file_metadata": ["file", "exiftool", "strings", "xxd", "hexdump", "binwalk"],
    "carving": ["foremost", "scalpel", "photorec", "testdisk"],
    "stego": ["zsteg", "steghide", "stegoveritas", "stegsolve", "aperisolve"],
    "memory": ["volatility3", "vol", "rekall"],
    "network": ["tshark", "tcpdump", "zeek", "networkminer", "rita"],
    "media": ["ffmpeg", "identify", "convert"],
    "usb_disk": ["usbrip", "autopsy"],
}

FORENSICS_PYTHON_MODULES = ["PIL", "scapy", "volatility3", "numpy"]

FORENSICS_TOOLCHAIN_CATALOG = {
    "triage": ["HexStrike AI", "file", "exiftool", "binwalk", "strings", "xxd"],
    "carving_recovery": ["foremost", "scalpel", "testdisk", "photorec", "Autopsy"],
    "stego": ["zsteg", "steghide", "StegoVeritas", "StegSolve", "AperiSolve", "stego-toolkit"],
    "memory": ["Volatility3", "Rekall"],
    "network": ["tshark", "Wireshark", "Zeek", "NetworkMiner", "RITA"],
}

REVERSE_COMMAND_GROUPS = {
    "binary_basics": ["file", "strings", "readelf", "objdump", "nm", "ltrace", "strace"],
    "disassemblers": ["rizin", "radare2", "r2", "ghidraRun", "cutter", "ida64", "binaryninja"],
    "symbolic": ["angr", "qiling", "triton", "manticore"],
    "emulation": ["unicorn", "qemu-x86_64", "qemu-aarch64"],
    "dotnet_java_android": ["de4dot", "jadx", "apktool", "jeb"],
}

REVERSE_PYTHON_MODULES = ["angr", "qiling", "triton", "unicorn", "capstone", "keystone"]

REVERSE_TOOLCHAIN_CATALOG = {
    "static_cli": ["file", "strings", "readelf", "objdump", "nm", "radare2/rizin"],
    "decompile_gui": ["Ghidra", "Binary Ninja", "IDA Pro", "Cutter", "JEB"],
    "symbolic_emulation": ["angr", "qangr", "Triton", "Qiling", "Unicorn", "rex"],
    "rop_bridge": ["angrop", "ROPgadget", "ropper"],
    "managed_mobile": ["de4dot", "Simplify", "jadx", "apktool"],
}

META_TOOLCHAIN_CATALOG = {
    "ctf_suites": ["CTF-Toolkit", "CTF-Recommended-Tools", "CTF-Tools", "Awesome-CTF"],
    "agentic_helpers": ["LiveExploit", "PwnAI", "Koshary", "KryptoPilot", "CookieFarm"],
    "policy": ["safe local first", "artifact logging", "approval for scans/exploit/installs"],
}

TOOLCHAIN_DEFINITIONS = {
    "pwn": (PWN_COMMAND_GROUPS, PWN_PYTHON_MODULES, PWN_TOOLCHAIN_CATALOG),
    "web": (WEB_COMMAND_GROUPS, WEB_PYTHON_MODULES, WEB_TOOLCHAIN_CATALOG),
    "crypto": (CRYPTO_COMMAND_GROUPS, CRYPTO_PYTHON_MODULES, CRYPTO_TOOLCHAIN_CATALOG),
    "forensics": (FORENSICS_COMMAND_GROUPS, FORENSICS_PYTHON_MODULES, FORENSICS_TOOLCHAIN_CATALOG),
    "reverse": (REVERSE_COMMAND_GROUPS, REVERSE_PYTHON_MODULES, REVERSE_TOOLCHAIN_CATALOG),
}

RISKY_FRAGMENTS = [
    ("install_package", ["apt install", "apt-get install", "pip install", "gem install", "npm install"]),
    ("docker_build", ["docker build", "docker compose build", "docker-compose build"]),
    ("destructive_delete", ["rm -rf", "shred", "wipefs"]),
    ("privileged_command", ["sudo ", "su -"]),
    ("broad_network_scan", ["masscan", "nmap -p-", "nmap --script"]),
    ("remote_shell_pipe", ["curl | sh", "curl -fsSL", "wget | sh"]),
]


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _goal_dir(goal_id: str) -> Path:
    if not goal_id.startswith("goal_"):
        raise ValueError("Invalid goal_id.")
    safe = "".join(c for c in goal_id if c.isalnum() or c in "_-")
    if safe != goal_id:
        raise ValueError("Invalid goal_id.")
    return AGENT_GOALS_DIR / goal_id


def _goal_path(goal_id: str) -> Path:
    return _goal_dir(goal_id) / "goal.json"


def _timeline_path(goal_id: str) -> Path:
    return _goal_dir(goal_id) / "timeline.jsonl"


def _artifacts_dir(goal_id: str) -> Path:
    path = _goal_dir(goal_id) / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_goal(goal_id: str) -> dict[str, Any]:
    path = _goal_path(goal_id)
    if not path.exists():
        raise FileNotFoundError(f"Goal not found: {goal_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_goal(goal: dict[str, Any]) -> None:
    goal["updated_at"] = _utc_now()
    path = _goal_path(goal["goal_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.parent / "artifacts").mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(goal, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_event(goal_id: str, event: dict[str, Any]) -> None:
    path = _timeline_path(goal_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ts": _utc_now(), **event}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    try:
        from app import event_bus
        event_bus.publish(goal_id, payload)
    except Exception:
        pass


def _read_timeline(goal_id: str) -> list[dict[str, Any]]:
    path = _timeline_path(goal_id)
    if not path.exists():
        return []
    events = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return events


def _action_fingerprint(goal_id: str, action: dict) -> str:
    import hashlib
    # Extract identifying fields of the action/event
    payload = json.dumps({
        "kind": action.get("kind"),
        "action": action.get("action"),
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _is_looping(goal_id: str, action: dict, window: int = 5) -> bool:
    recent = _read_timeline(goal_id)[-window:]
    fp = _action_fingerprint(goal_id, action)
    return sum(1 for e in recent if _action_fingerprint(goal_id, e) == fp) >= 2


def _risk_matches(text: str) -> list[dict[str, str]]:
    lower = text.lower()
    matches = []
    for rule, fragments in RISKY_FRAGMENTS:
        for fragment in fragments:
            if fragment in lower:
                matches.append({"rule": rule, "matched_fragment": fragment})
    return matches


def _validate_scope(goal: dict[str, Any], path_or_host: str, is_path: bool = True) -> bool:
    scope = goal.get("scope", {})
    if is_path:
        allowed_paths = scope.get("allowed_paths", [])
        if not allowed_paths:
            return False
        try:
            target_path = Path(path_or_host).resolve()
        except Exception:
            return False
        for p in allowed_paths:
            try:
                allowed_p = Path(p).resolve()
                if target_path == allowed_p or allowed_p in target_path.parents:
                    return True
            except Exception:
                continue
        return False
    else:
        allowed_hosts = scope.get("allowed_hosts", [])
        if not allowed_hosts:
            return False
        host = path_or_host.strip().lower()
        if host in ("", "localhost", "127.0.0.1"):
            return True
        for h in allowed_hosts:
            allowed_h = h.strip().lower()
            if allowed_h.startswith("*."):
                suffix = allowed_h[1:]
                if host.endswith(suffix):
                    return True
            elif host == allowed_h or host.endswith("." + allowed_h):
                return True
        return False


def _normalize_budget(budget: dict[str, Any] | None) -> dict[str, int]:
    budget = budget or {}
    return {
        "max_steps": int(budget.get("max_steps", DEFAULT_MAX_STEPS)),
        "max_seconds": int(budget.get("max_seconds", DEFAULT_MAX_SECONDS)),
    }


def _normalize_scope(scope: dict[str, Any] | None, cwd: str) -> dict[str, Any]:
    scope = dict(scope or {})
    allowed_paths = scope.get("allowed_paths") or []
    if cwd:
        allowed_paths = [cwd, *allowed_paths]
    scope["allowed_paths"] = allowed_paths
    scope.setdefault("allowed_hosts", [])
    scope.setdefault("approval_required_for", [
        "install_package",
        "docker_build",
        "destructive_delete",
        "privileged_command",
        "broad_network_scan",
        "remote_shell_pipe",
    ])
    return scope


def _elapsed_seconds(goal: dict[str, Any]) -> int:
    return int(time.time() - float(goal.get("created_epoch", time.time())))


def _budget_exhausted(goal: dict[str, Any]) -> str:
    budget = goal["budget"]
    if goal["steps_taken"] >= budget["max_steps"]:
        return "max_steps_exceeded"
    if _elapsed_seconds(goal) >= budget["max_seconds"]:
        return "max_seconds_exceeded"
    return ""


def _event_kinds(goal_id: str) -> set[str]:
    return {event.get("kind", "") for event in _read_timeline(goal_id)}


def _summarize_goal(goal: dict[str, Any]) -> dict[str, Any]:
    events = _read_timeline(goal["goal_id"])
    return {
        "ok": True,
        "goal_id": goal["goal_id"],
        "objective": goal["objective"],
        "status": goal["status"],
        "cwd": goal["cwd"],
        "steps_taken": goal["steps_taken"],
        "budget": goal["budget"],
        "elapsed_seconds": _elapsed_seconds(goal),
        "timeline_events": len(events),
        "last_event": events[-1] if events else None,
    }


def _list_cwd(cwd: str) -> dict[str, Any]:
    resolved = resolve_agent_path(cwd or ".")
    items = []
    for item in sorted(resolved.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:80]:
        items.append({
            "name": item.name,
            "is_directory": item.is_dir(),
            "size_bytes": 0 if item.is_dir() else item.stat().st_size,
        })
    return {"path": str(resolved), "items": items}


def _command_exists(command: str) -> str:
    found = shutil.which(command)
    if found:
        return found
    extra_dirs = [
        BASE_DIR / ".venv" / "bin",
        Path.home() / ".local" / "bin",
        Path.home() / ".local" / "share" / "gem" / "ruby" / "3.3.0" / "bin",
        Path.home() / "miniforge3" / "envs" / "sage" / "bin",
    ]
    for directory in extra_dirs:
        candidate = directory / command
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return ""


def _tool_status(commands: list[str]) -> dict[str, Any]:
    return {command: {"available": bool(path := _command_exists(command)), "path": path} for command in commands}


def _python_module_status(modules: list[str]) -> dict[str, Any]:
    status = {}
    for module in modules:
        try:
            __import__(module)
            status[module] = {"available": True}
        except Exception as exc:
            status[module] = {"available": False, "error": exc.__class__.__name__}
    return status


def _command_status_by_group(groups: dict[str, list[str]]) -> dict[str, Any]:
    return {group: _tool_status(commands) for group, commands in groups.items()}


def _pwn_command_status_by_group() -> dict[str, Any]:
    return _command_status_by_group(PWN_COMMAND_GROUPS)


def _missing_recommended_tools(recommended: list[str], python_modules: list[str]) -> list[str]:
    missing = []
    command_status = _tool_status([t for t in recommended if t not in python_modules])
    module_status = _python_module_status([t for t in recommended if t in python_modules])
    for name, data in command_status.items():
        if not data["available"]:
            missing.append(name)
    for name, data in module_status.items():
        if not data["available"]:
            missing.append(name)
    return missing


def _pwn_missing_recommended_tools() -> list[str]:
    return _missing_recommended_tools(
        ["patchelf", "pwninit", "rp++", "msfvenom", "ptrlib", "angr", "qiling"],
        PWN_PYTHON_MODULES,
    )


def _toolchain_score(groups: dict[str, list[str]], modules: list[str]) -> dict[str, Any]:
    commands = sorted({command for commands in groups.values() for command in commands})
    command_status = _tool_status(commands)
    module_status = _python_module_status(modules)
    total = len(command_status) + len(module_status)
    available = sum(1 for data in command_status.values() if data["available"])
    available += sum(1 for data in module_status.values() if data["available"])
    score = round((available / total) * 100, 1) if total else 0.0
    return {
        "available": available,
        "total": total,
        "score_percent": score,
        "grade": "ready" if score >= 55 else "partial" if score >= 25 else "thin",
    }


def _toolchain_capability(category: str, status: str, stages: list[str], recommended: list[str]) -> dict[str, Any]:
    groups, modules, catalog = TOOLCHAIN_DEFINITIONS[category]
    return {
        "status": status,
        "stages": stages,
        "catalog": catalog,
        "command_groups": _command_status_by_group(groups),
        "python_modules": _python_module_status(modules),
        "missing_recommended": _missing_recommended_tools(recommended, modules),
        "evaluation": _toolchain_score(groups, modules),
        "safety_model": {
            "auto": "local triage/recon only",
            "approval_required": ["install", "fuzzing", "broad scan", "exploit", "unknown remote host"],
        },
    }


def _safe_artifact_name(label: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in label).strip("-") or "artifact"


def _run_toolchain_command(goal: dict[str, Any], label: str, command: list[str], cwd: Path, timeout: int = 20) -> dict[str, Any]:
    # Enforce remaining budget time limit on subprocess execution
    remaining = goal["budget"]["max_seconds"] - _elapsed_seconds(goal)
    timeout = min(timeout, max(2, remaining))

    artifact_dir = _artifacts_dir(goal["goal_id"])
    safe_label = _safe_artifact_name(label)
    stdout_path = artifact_dir / f"{safe_label}.stdout.txt"
    stderr_path = artifact_dir / f"{safe_label}.stderr.txt"
    meta_path = artifact_dir / f"{safe_label}.json"

    started = time.monotonic()
    resolved_command = list(command)
    command_path = _command_exists(resolved_command[0])
    if command_path:
        resolved_command[0] = command_path
    try:
        proc = subprocess.run(
            resolved_command,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        exit_code = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace")
        stderr += f"\n[agent-toolchain] TIMEOUT after {timeout}s\n"
        timed_out = True

    stdout = stdout[:MAX_TOOLCHAIN_OUTPUT]
    stderr = stderr[:MAX_TOOLCHAIN_OUTPUT]
    stdout_path.write_text(stdout, encoding="utf-8", errors="replace")
    stderr_path.write_text(stderr, encoding="utf-8", errors="replace")

    meta = {
        "label": label,
        "command": command,
        "resolved_command": resolved_command,
        "cwd": str(cwd),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_sec": round(time.monotonic() - started, 3),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stdout_preview": stdout[:1600],
        "stderr_preview": stderr[:1600],
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def _find_pwn_binaries(cwd: str) -> list[dict[str, Any]]:
    root = resolve_agent_path(cwd or ".")
    candidates = []
    skip_parts = {".git", ".venv", "__pycache__", "node_modules", "logs", "workspaces"}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_parts for part in path.parts):
            continue
        if path.stat().st_size > 50_000_000:
            continue
        try:
            head = path.read_bytes()[:4]
        except OSError:
            continue
        executable = os.access(path, os.X_OK)
        interesting_name = path.name.lower() in {"chall", "challenge", "vuln", "pwn", "server"}
        if head == b"\x7fELF" or executable or interesting_name:
            candidates.append({
                "path": str(path),
                "relative_path": str(path.relative_to(root)),
                "size_bytes": path.stat().st_size,
                "is_elf": head == b"\x7fELF",
                "executable": executable,
            })
    return sorted(candidates, key=lambda item: (not item["is_elf"], item["size_bytes"]))[:20]


def _select_binary(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    for candidate in candidates:
        if candidate["is_elf"]:
            return candidate
    return candidates[0] if candidates else None


def _find_libc_files(cwd: str) -> list[str]:
    root = resolve_agent_path(cwd or ".")
    return [str(p) for p in root.rglob("libc*.so*") if p.is_file()][:5]


def _candidate_files(cwd: str, suffixes: set[str] | None = None, max_files: int = 20) -> list[dict[str, Any]]:
    root = resolve_agent_path(cwd or ".")
    suffixes = {suffix.lower() for suffix in (suffixes or set())}
    skip_parts = {".git", ".venv", "__pycache__", "node_modules", "logs", "workspaces"}
    candidates = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_parts for part in path.parts):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > 50_000_000:
            continue
        if suffixes and path.suffix.lower() not in suffixes:
            continue
        candidates.append({"path": str(path), "relative_path": str(path.relative_to(root)), "size_bytes": size})
    return sorted(candidates, key=lambda item: item["size_bytes"])[:max_files]


def _extract_urls(text: str) -> list[str]:
    import re

    return sorted(set(re.findall(r"https?://[^\s'\"<>]+", text)))


def _tool_status_action(category: str, goal: dict[str, Any]) -> dict[str, Any]:
    groups, modules, catalog = TOOLCHAIN_DEFINITIONS[category]
    return {
        "kind": f"{category}_tool_status",
        "action": f"{category}_toolchain_status",
        "observation": {
            "ok": True,
            "command_groups": _command_status_by_group(groups),
            "python_modules": _python_module_status(modules),
            "catalog": catalog,
            "evaluation": _toolchain_score(groups, modules),
            "safety_note": "Only safe local recon is automatic; aggressive scans/exploits require approval.",
        },
    }


def _write_toolchain_summary(goal: dict[str, Any], category: str, next_steps: list[str]) -> dict[str, Any]:
    artifact_dir = _artifacts_dir(goal["goal_id"])
    summary_path = artifact_dir / f"{category}_toolchain_summary.md"
    events = _read_timeline(goal["goal_id"])
    lines = [
        f"# {category.title()} Toolchain Summary",
        "",
        f"- Objective: {goal['objective']}",
        f"- CWD: `{goal['cwd']}`",
        "",
        "## Completed stages",
    ]
    for event in events:
        if str(event.get("kind", "")).startswith(f"{category}_"):
            lines.append(f"- `{event.get('kind')}` via `{event.get('action')}`")
    lines.extend(["", "## Recommended next steps", *[f"- {step}" for step in next_steps]])
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "kind": f"{category}_summary",
        "action": f"{category}_toolchain_summary",
        "complete": True,
        "observation": {"ok": True, "summary_path": str(summary_path)},
    }


def _local_file_recon_action(goal: dict[str, Any], category: str, suffixes: set[str] | None = None) -> dict[str, Any]:
    if category == "reverse":
        candidates = _find_pwn_binaries(goal["cwd"]) or _candidate_files(goal["cwd"], suffixes=suffixes)
    else:
        candidates = _candidate_files(goal["cwd"], suffixes=suffixes)
    results = []
    for item in candidates[:5]:
        path = Path(item["path"])
        cwd = path.parent
        commands = [("file", ["file", str(path)]), ("strings", ["strings", "-a", "-n", "5", str(path)])]
        if category == "forensics":
            commands.extend([("exiftool", ["exiftool", str(path)]), ("binwalk", ["binwalk", str(path)])])
        if category == "reverse":
            commands.extend([("readelf-header", ["readelf", "-h", str(path)]), ("objdump-header", ["objdump", "-f", str(path)])])
        for label, command in commands:
            if not _command_exists(command[0]):
                results.append({"label": label, "file": str(path), "missing_tool": command[0]})
                continue
            results.append(_run_toolchain_command(goal, f"{category}-{label}-{path.name}", command, cwd, timeout=20))
    return {
        "kind": f"{category}_recon",
        "action": f"{category}_safe_local_recon",
        "observation": {
            "ok": True,
            "candidate_files": candidates,
            "commands": results,
            "summary": "Local safe recon completed." if candidates else "No matching local files found.",
        },
    }


def _web_recon_action(goal: dict[str, Any]) -> dict[str, Any]:
    urls = _extract_urls(goal["objective"])
    scope_urls = goal.get("scope", {}).get("urls") or []
    urls = sorted(set([*urls, *scope_urls]))
    
    # Validate each URL host against allowed_hosts scope
    from urllib.parse import urlparse
    for url in urls:
        try:
            parsed = urlparse(url if "://" in url else f"http://{url}")
            host = parsed.hostname or url
            if ":" in host:
                host = host.split(":")[0]
            if not _validate_scope(goal, host, is_path=False):
                return {
                    "kind": "out_of_scope",
                    "action": "skip",
                    "observation": {
                        "ok": False,
                        "reason": f"URL host '{host}' is out of scope (allowed_hosts: {goal.get('scope', {}).get('allowed_hosts', [])})."
                    },
                    "complete": True
                }
        except Exception as e:
            return {
                "kind": "out_of_scope",
                "action": "skip",
                "observation": {
                    "ok": False,
                    "reason": f"Could not parse URL '{url}': {e}"
                },
                "complete": True
            }

    artifact_dir = _artifacts_dir(goal["goal_id"])
    plan_path = artifact_dir / "web_recon_plan.md"
    target_lines = [f"- {url}" for url in urls] if urls else ["- No URL in objective/scope."]
    lines = [
        "# Web Safe Recon Plan",
        "",
        "Automatic mode does not fuzz or scan remote hosts.",
        "",
        "## Targets",
        *target_lines,
        "",
        "## Approval-gated commands",
        "- ffuf / gobuster / feroxbuster content discovery",
        "- nuclei / sqlmap / xsstrike vulnerability probes",
        "- nmap broad scans",
    ]
    plan_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "kind": "web_recon",
        "action": "web_safe_recon_plan",
        "observation": {"ok": True, "urls": urls, "plan_path": str(plan_path)},
    }


def _generic_chain_next_action(
    goal: dict[str, Any],
    kinds: set[str],
    category: str,
    suffixes: set[str] | None,
    next_steps: list[str],
) -> dict[str, Any] | None:
    if _category_from_goal(goal) != category:
        return None
    if f"{category}_tool_status" not in kinds:
        return _tool_status_action(category, goal)
    if f"{category}_recon" not in kinds:
        if category == "web":
            return _web_recon_action(goal)
        return _local_file_recon_action(goal, category, suffixes=suffixes)
    if f"{category}_summary" not in kinds:
        return _write_toolchain_summary(goal, category, next_steps)
    return None


def _write_pwn_solve_template(goal: dict[str, Any], binary: Path) -> dict[str, Any]:
    artifact_dir = _artifacts_dir(goal["goal_id"])
    template_path = artifact_dir / "solve_pwn_template.py"
    rel_binary = binary.name
    template = f"""#!/usr/bin/env python3
from pwn import *

context.binary = './{rel_binary}'
elf = context.binary

HOST = args.HOST or 'localhost'
PORT = int(args.PORT or 31337)
REMOTE = args.REMOTE

def start():
    if REMOTE:
        return remote(HOST, PORT)
    return process([elf.path])

def main():
    io = start()
    # TODO: fill offset/leak/ROP after reviewing artifacts from this toolchain.
    io.interactive()

if __name__ == '__main__':
    main()
"""
    template_path.write_text(template, encoding="utf-8")
    return {"path": str(template_path), "binary": str(binary)}


def _pwn_recon_action(goal: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    selected = _select_binary(candidates)
    if not selected:
        return {
            "kind": "pwn_recon",
            "action": "pwn_toolchain_recon",
            "observation": {
                "ok": False,
                "summary": "No candidate ELF/executable found in cwd.",
                "candidates": candidates,
            },
        }

    binary = Path(selected["path"])
    cwd = binary.parent
    commands = [
        ("file", ["file", str(binary)]),
        ("checksec", ["checksec", "--file", str(binary)]),
        ("readelf-header", ["readelf", "-h", str(binary)]),
        ("readelf-symbols", ["readelf", "-s", str(binary)]),
        ("strings", ["strings", "-a", "-n", "5", str(binary)]),
    ]
    results = []
    for label, command in commands:
        if not _command_exists(command[0]):
            results.append({"label": label, "missing_tool": command[0]})
            continue
        results.append(_run_toolchain_command(goal, f"pwn-{label}", command, cwd))

    template = _write_pwn_solve_template(goal, binary)
    return {
        "kind": "pwn_recon",
        "action": "pwn_toolchain_recon",
        "observation": {
            "ok": True,
            "selected_binary": selected,
            "candidates": candidates,
            "commands": results,
            "solve_template": template,
        },
    }


def _pwn_gadget_action(goal: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    selected = _select_binary(candidates)
    if not selected:
        return {
            "kind": "pwn_gadgets",
            "action": "pwn_toolchain_gadgets",
            "observation": {"ok": False, "summary": "No candidate binary available for gadget scan."},
        }
    binary = Path(selected["path"])
    cwd = binary.parent
    commands = [
        ("ropgadget", ["ROPgadget", "--binary", str(binary)]),
        ("ropper-pop-rdi", ["ropper", "-f", str(binary), "--search", "pop rdi"]),
    ]
    results = []
    for label, command in commands:
        if not _command_exists(command[0]):
            results.append({"label": label, "missing_tool": command[0]})
            continue
        results.append(_run_toolchain_command(goal, f"pwn-{label}", command, cwd, timeout=45))
    return {
        "kind": "pwn_gadgets",
        "action": "pwn_toolchain_gadgets",
        "observation": {
            "ok": True,
            "selected_binary": selected,
            "commands": results,
        },
    }


def _pwn_libc_action(goal: dict[str, Any]) -> dict[str, Any]:
    libc_files = _find_libc_files(goal["cwd"])
    results = []
    for libc in libc_files[:2]:
        if _command_exists("one_gadget"):
            results.append(_run_toolchain_command(goal, f"pwn-one-gadget-{Path(libc).name}", ["one_gadget", libc], Path(libc).parent, timeout=45))
    return {
        "kind": "pwn_libc",
        "action": "pwn_toolchain_libc",
        "observation": {
            "ok": True,
            "libc_files": libc_files,
            "commands": results,
            "summary": "No libc files found." if not libc_files else "Libc helper scan completed.",
        },
    }


def _pwn_summary_action(goal: dict[str, Any]) -> dict[str, Any]:
    artifact_dir = _artifacts_dir(goal["goal_id"])
    summary_path = artifact_dir / "pwn_toolchain_summary.md"
    events = _read_timeline(goal["goal_id"])
    lines = [
        "# Pwn Toolchain Summary",
        "",
        f"- Objective: {goal['objective']}",
        f"- CWD: `{goal['cwd']}`",
        "",
        "## Completed stages",
    ]
    for event in events:
        if str(event.get("kind", "")).startswith("pwn_"):
            lines.append(f"- `{event.get('kind')}` via `{event.get('action')}`")
    lines.extend([
        "",
        "## Next manual exploit steps",
        "- Review `pwn-checksec.stdout.txt` to choose exploit strategy.",
        "- Use `pwn-ropgadget.stdout.txt` / `pwn-ropper-pop-rdi.stdout.txt` for ROP chains.",
        "- Fill `solve_pwn_template.py` with offset, leak, libc base, and final payload.",
        "- Run locally first, then remote only after a working primitive exists.",
    ])
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "kind": "pwn_summary",
        "action": "pwn_toolchain_summary",
        "complete": True,
        "observation": {"ok": True, "summary_path": str(summary_path)},
    }


def _category_from_goal(goal: dict[str, Any]) -> str:
    scope_category = str(goal.get("scope", {}).get("category", "")).lower()
    objective = goal["objective"].lower()
    if scope_category:
        return "reverse" if scope_category == "rev" else scope_category
    category_keywords = [
        ("web", ["web", "http://", "https://", "xss", "sqli", "ssrf", "csrf", "lfi", "rfi"]),
        ("crypto", ["crypto", "rsa", "aes", "ecc", "lattice", "cipher", "hash", "oracle", "sage"]),
        ("forensics", ["forensics", "forensic", "pcap", "memory dump", "stego", "image", "metadata"]),
        ("reverse", ["reverse", "rev", "reversing", "decompile", "crackme", "apk", "malware"]),
        ("pwn", ["pwn", "heap", "rop", "ret2libc", "overflow", "shellcode"]),
    ]
    for category, keywords in category_keywords:
        if any(keyword in objective for keyword in keywords):
            return category
    root = resolve_agent_path(goal["cwd"] or ".")
    forensic_suffixes = {".pcap", ".pcapng", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".wav", ".mp3", ".zip", ".7z", ".rar", ".raw", ".dump", ".dmp"}
    crypto_suffixes = {".sage", ".sobj", ".pem", ".pub", ".key", ".enc", ".cipher", ".ct"}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in crypto_suffixes:
            return "crypto"
        if suffix in forensic_suffixes:
            return "forensics"
    candidates = _find_pwn_binaries(goal["cwd"])
    if any(candidate["is_elf"] for candidate in candidates):
        return "pwn"
    return ""


def _pwn_chain_next_action(goal: dict[str, Any], kinds: set[str]) -> dict[str, Any] | None:
    category = _category_from_goal(goal)
    if category != "pwn":
        return None
    candidates = _find_pwn_binaries(goal["cwd"])
    if "pwn_tool_status" not in kinds:
        return {
            "kind": "pwn_tool_status",
            "action": "pwn_toolchain_status",
            "observation": {
                "ok": True,
                "command_groups": _pwn_command_status_by_group(),
                "python_modules": _python_module_status(PWN_PYTHON_MODULES),
                "catalog": PWN_TOOLCHAIN_CATALOG,
                "missing_recommended": _pwn_missing_recommended_tools(),
                "candidate_binaries": candidates,
            },
        }
    if "pwn_recon" not in kinds:
        return _pwn_recon_action(goal, candidates)
    if "pwn_gadgets" not in kinds:
        return _pwn_gadget_action(goal, candidates)
    if "pwn_libc" not in kinds:
        return _pwn_libc_action(goal)
    if "pwn_summary" not in kinds:
        return _pwn_summary_action(goal)
    return None


def _run_next_safe_action(goal: dict[str, Any]) -> dict[str, Any]:
    goal_id = goal["goal_id"]
    cwd = goal["cwd"]
    
    # Scope check on cwd path
    if not _validate_scope(goal, cwd, is_path=True):
        return {
            "kind": "out_of_scope",
            "action": "skip",
            "observation": {
                "ok": False,
                "reason": f"Path '{cwd}' is out of scope (allowed_paths: {goal.get('scope', {}).get('allowed_paths', [])})."
            },
            "complete": True
        }

    kinds = _event_kinds(goal_id)
    objective = goal["objective"].lower()

    if "instructions_loaded" not in kinds and ("ctf" in objective or "harness" in objective or "flag" in objective):
        instructions = ctf_harness_instructions(max_chars=6000)
        return {
            "kind": "instructions_loaded",
            "action": "ctf_harness_instructions",
            "observation": {
                "ok": instructions.get("ok"),
                "summary": instructions.get("summary"),
                "path": instructions.get("path"),
                "truncated": instructions.get("truncated"),
            },
        }

    pwn_action = _pwn_chain_next_action(goal, kinds)
    if pwn_action:
        return pwn_action

    for category, suffixes, next_steps in [
        ("web", None, [
            "Confirm target scope/hosts before running scanners.",
            "Use browser/manual proof first, then approved ffuf/nuclei/sqlmap only when scoped.",
            "Save request/response evidence for any flag or vulnerability claim.",
        ]),
        ("crypto", {".txt", ".sage", ".py", ".pem", ".pub", ".key", ".enc", ".cipher", ".ct"}, [
            "Classify primitive and parameters before brute force.",
            "Prefer Sage/Z3/math proof over blind guessing.",
            "Keep solve script deterministic and document recovered secrets.",
        ]),
        ("forensics", {".pcap", ".pcapng", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".wav", ".mp3", ".zip", ".7z", ".rar", ".raw", ".dump", ".dmp"}, [
            "Review metadata/carving output before extraction-heavy steps.",
            "Use stego/memory/network tools only on matching artifact types.",
            "Preserve original evidence and write recovered files under artifacts.",
        ]),
        ("reverse", None, [
            "Start with strings/imports/control-flow before decompiler-heavy work.",
            "Use Ghidra/angr/Qiling only after static triage identifies a target path.",
            "Produce a local checker/patch/solve script before remote use.",
        ]),
    ]:
        action = _generic_chain_next_action(goal, kinds, category, suffixes, next_steps)
        if action:
            return action

    ctf_yaml = resolve_agent_path(cwd or ".") / "ctf.yaml"
    if ctf_yaml.exists() and "harness_checked" not in kinds:
        check = ctf_harness_check(cwd=cwd)
        return {
            "kind": "harness_checked",
            "action": "ctf_harness_check",
            "observation": {
                "ok": check.get("ok"),
                "exit_code": check.get("exit_code"),
                "stdout_preview": (check.get("stdout") or "")[:1200],
                "stderr_preview": (check.get("stderr") or "")[:1200],
            },
        }

    if "cwd_inspected" not in kinds:
        listing = _list_cwd(cwd)
        return {
            "kind": "cwd_inspected",
            "action": "list_directory",
            "observation": listing,
        }

    if "policy_checked" not in kinds:
        policy = policy_check_command("pwd && ls -la", cwd=cwd)
        return {
            "kind": "policy_checked",
            "action": "policy_check_command",
            "observation": policy,
        }

    return {
        "kind": "decision_point",
        "action": "pause",
        "observation": {
            "ok": True,
            "summary": "Assisted autonomous MVP reached a safe decision point. Provide the next objective or call a specific tool.",
        },
        "complete": True,
    }


@mcp.tool(name="agent_goal_create", description="Create a budgeted assisted-autonomous goal with scoped technical state.")
def agent_goal_create(
    objective: str,
    cwd: str = "",
    scope: dict[str, Any] | None = None,
    budget: dict[str, Any] | None = None,
) -> dict:
    try:
        if not objective.strip():
            raise ValueError("objective must not be empty")
        resolved_cwd = resolve_agent_path(cwd or ".")
        if not resolved_cwd.exists() or not resolved_cwd.is_dir():
            raise FileNotFoundError(f"cwd not found: {resolved_cwd}")

        goal_id = f"goal_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        goal = {
            "goal_id": goal_id,
            "objective": objective.strip(),
            "cwd": str(resolved_cwd),
            "status": "active",
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "created_epoch": time.time(),
            "steps_taken": 0,
            "budget": _normalize_budget(budget),
            "scope": _normalize_scope(scope, str(resolved_cwd)),
            "risk_matches": _risk_matches(objective),
        }
        _save_goal(goal)
        _append_event(goal_id, {"kind": "goal_created", "objective": goal["objective"], "cwd": goal["cwd"]})
        log_audit_event("AGENT_GOAL_CREATE", {"goal_id": goal_id, "cwd": goal["cwd"]})
        return {**_summarize_goal(goal), "scope": goal["scope"], "risk_matches": goal["risk_matches"]}
    except Exception as e:
        log_audit_event("AGENT_GOAL_CREATE_FAIL", {"error": str(e)})
        return format_error_response(e)


@mcp.tool(name="agent_toolchain_capabilities", description="Return autonomous agent CTF toolchain stages and local tool availability.")
def agent_toolchain_capabilities() -> dict:
    try:
        return {
            "ok": True,
            "toolchains": {
                "pwn": _toolchain_capability(
                    "pwn",
                    "implemented",
                    ["tool_status", "recon", "gadget_scan", "libc_scan", "summary"],
                    ["patchelf", "pwninit", "rp++", "msfvenom", "ptrlib", "angr", "qiling"],
                ),
                "web": _toolchain_capability(
                    "web",
                    "implemented_safe_recon",
                    ["tool_status", "safe_recon_plan", "summary"],
                    ["curl", "whatweb", "ffuf", "nuclei", "sqlmap", "playwright"],
                ),
                "crypto": _toolchain_capability(
                    "crypto",
                    "implemented_safe_recon",
                    ["tool_status", "local_file_recon", "summary"],
                    ["sage", "RsaCtfTool", "z3", "Crypto", "gmpy2", "hashcat", "john"],
                ),
                "forensics": _toolchain_capability(
                    "forensics",
                    "implemented_safe_recon",
                    ["tool_status", "local_file_recon", "summary"],
                    ["exiftool", "binwalk", "foremost", "tshark", "zsteg", "volatility3"],
                ),
                "reverse": _toolchain_capability(
                    "reverse",
                    "implemented_safe_recon",
                    ["tool_status", "local_binary_recon", "summary"],
                    ["rizin", "radare2", "ghidraRun", "angr", "qiling", "capstone"],
                ),
                "meta": {
                    "status": "cataloged",
                    "catalog": META_TOOLCHAIN_CATALOG,
                    "evaluation": "not scored: meta suites are references/workflow packs, not required runtime tools",
                },
            },
        }
    except Exception as e:
        return format_error_response(e)


@mcp.tool(name="agent_step", description="Run one safe assisted-autonomous plan/act/observe/persist step.")
async def agent_step(goal_id: str, approval: str = "auto_safe") -> dict:
    try:
        goal = _load_goal(goal_id)
        if goal["status"] in {"cancelled", "completed", "blocked"}:
            return {**_summarize_goal(goal), "message": f"goal is {goal['status']}"}

        exhausted = _budget_exhausted(goal)
        if exhausted:
            goal["status"] = "blocked"
            _save_goal(goal)
            _append_event(goal_id, {"kind": "budget_exhausted", "reason": exhausted})
            return {**_summarize_goal(goal), "blocked_reason": exhausted}

        risks = goal.get("risk_matches", [])
        if risks and approval != "approved":
            from app import event_bus
            goal["status"] = "needs_approval"
            _save_goal(goal)
            event = {
                "kind": "needs_approval",
                "reason": "objective_contains_high_risk_fragments",
                "risk_matches": risks,
                "required_approval": "approved",
            }
            _append_event(goal_id, event)  # publish tới SSE nếu có subscriber, no-op nếu không
            log_audit_event("AGENT_STEP_NEEDS_APPROVAL", {"goal_id": goal_id, "risk_matches": risks})

            fut = event_bus.register_approval(goal_id)
            try:
                import asyncio
                approved = await asyncio.wait_for(fut, timeout=60.0)
                if approved:
                    approval = "approved"
                    goal["status"] = "active"
                    _save_goal(goal)
                    _append_event(goal_id, {"kind": "approval_recorded", "approval": "approved"})
                else:
                    return {**_summarize_goal(goal), **event, "message": "Approval rejected by client."}
            except asyncio.TimeoutError:
                # Timeout: xóa Future khỏi registry, để GPT gọi agent_approve sau nếu muốn
                from app.event_bus import _approvals
                _approvals.pop(goal_id, None)
                return {**_summarize_goal(goal), **event, "message": "Approval request timed out after 60s. Call agent_approve to resume."}

        if goal["status"] == "needs_approval" and approval == "approved":
            goal["status"] = "active"
            _append_event(goal_id, {"kind": "approval_recorded", "approval": approval})

        # Check for near-exhausted budget
        remaining_seconds = goal["budget"]["max_seconds"] - _elapsed_seconds(goal)
        if remaining_seconds < 10:
            goal["status"] = "blocked"
            _save_goal(goal)
            exhaust_event = {
                "kind": "budget_near_exhaustion",
                "action": "skip",
                "observation": {
                    "ok": False,
                    "reason": f"Only {remaining_seconds} seconds remaining in budget. Execution aborted to avoid incomplete actions."
                }
            }
            _append_event(goal_id, exhaust_event)
            log_audit_event("AGENT_STEP_NEAR_EXHAUSTION", {"goal_id": goal_id, "remaining_seconds": remaining_seconds})
            return {**_summarize_goal(goal), "blocked_reason": "budget_near_exhaustion"}

        result = _run_next_safe_action(goal)

        # Loop detection check
        if _is_looping(goal_id, result):
            goal["status"] = "blocked"
            _save_goal(goal)
            loop_event = {
                "kind": "loop_detected",
                "action": result.get("action"),
                "observation": {
                    "ok": False,
                    "reason": f"Loop detected for action '{result.get('action')}' (kind '{result.get('kind')}'). Execution aborted."
                }
            }
            _append_event(goal_id, loop_event)
            log_audit_event("AGENT_LOOP_DETECTED", {"goal_id": goal_id, "action": result.get("action")})
            return {**_summarize_goal(goal), "blocked_reason": "loop_detected", "step": loop_event}

        goal["steps_taken"] += 1
        if result.get("complete"):
            goal["status"] = "completed"
        _save_goal(goal)
        _append_event(goal_id, result)
        log_audit_event("AGENT_STEP", {"goal_id": goal_id, "kind": result["kind"], "status": goal["status"]})
        return {**_summarize_goal(goal), "step": result}
    except Exception as e:
        log_audit_event("AGENT_STEP_FAIL", {"goal_id": goal_id, "error": str(e)})
        return format_error_response(e)


@mcp.tool(name="agent_goal_start", description="Start or resume continuous execution of an assisted-autonomous agent goal.")
async def agent_goal_start(goal_id: str, mode: str = "bounded_auto") -> dict:
    try:
        goal = _load_goal(goal_id)
        if goal["status"] in {"cancelled", "completed", "blocked"}:
            return {**_summarize_goal(goal), "message": f"goal is {goal['status']}"}

        max_steps = 1 if mode == "step" else goal["budget"]["max_steps"]
        steps_run = 0
        
        while steps_run < max_steps:
            goal = _load_goal(goal_id)
            if goal["status"] in {"cancelled", "completed", "blocked", "needs_approval"}:
                break
                
            step_res = await agent_step(goal_id)
            steps_run += 1
            
            updated_goal = _load_goal(goal_id)
            if updated_goal["status"] in {"cancelled", "completed", "blocked", "needs_approval"}:
                break
                
        return _summarize_goal(_load_goal(goal_id))
    except Exception as e:
        log_audit_event("AGENT_GOAL_START_FAIL", {"goal_id": goal_id, "error": str(e)})
        return format_error_response(e)


@mcp.tool(name="agent_status", description="Return current status and recent timeline for an assisted-autonomous goal.")
def agent_status(goal_id: str) -> dict:
    try:
        goal = _load_goal(goal_id)
        events = _read_timeline(goal_id)
        return {**_summarize_goal(goal), "recent_events": events[-10:]}
    except Exception as e:
        return format_error_response(e)


@mcp.tool(name="agent_cancel", description="Cancel an active assisted-autonomous goal.")
def agent_cancel(goal_id: str) -> dict:
    try:
        goal = _load_goal(goal_id)
        goal["status"] = "cancelled"
        _save_goal(goal)
        _append_event(goal_id, {"kind": "goal_cancelled"})
        log_audit_event("AGENT_CANCEL", {"goal_id": goal_id})
        return _summarize_goal(goal)
    except Exception as e:
        log_audit_event("AGENT_CANCEL_FAIL", {"goal_id": goal_id, "error": str(e)})
        return format_error_response(e)


@mcp.tool(name="agent_report", description="Generate and return a Markdown report for an assisted-autonomous goal.")
def agent_report(goal_id: str) -> dict:
    try:
        goal = _load_goal(goal_id)
        events = _read_timeline(goal_id)
        report_path = _goal_dir(goal_id) / "report.md"
        lines = [
            f"# Agent Goal Report: {goal_id}",
            "",
            f"- **Objective**: {goal['objective']}",
            f"- **Status**: `{goal['status']}`",
            f"- **CWD**: `{goal['cwd']}`",
            f"- **Steps**: `{goal['steps_taken']}`",
            f"- **Elapsed seconds**: `{_elapsed_seconds(goal)}`",
            "",
            "## Timeline",
        ]
        for event in events:
            lines.append(f"- `{event.get('ts')}` **{event.get('kind')}** `{event.get('action', '')}`")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _append_event(goal_id, {"kind": "report_generated", "path": str(report_path)})
        log_audit_event("AGENT_REPORT", {"goal_id": goal_id, "path": str(report_path)})
        return {**_summarize_goal(goal), "report_path": str(report_path), "content": report_path.read_text(encoding="utf-8")}
    except Exception as e:
        log_audit_event("AGENT_REPORT_FAIL", {"goal_id": goal_id, "error": str(e)})
        return format_error_response(e)


@mcp.tool(
    name="agent_approve",
    description=(
        "Approve a pending risky action for an assisted-autonomous goal. "
        "Call this after the user explicitly confirms they want to proceed. "
        "Returns immediately if no approval is pending."
    ),
)
def agent_approve(goal_id: str) -> dict:
    try:
        from app import event_bus
        goal = _load_goal(goal_id)
        if not event_bus.pending_approval(goal_id):
            return {
                **_summarize_goal(goal),
                "ok": False,
                "message": "No pending approval for this goal.",
            }
        event_bus.resolve_approval(goal_id, approved=True)
        _append_event(goal_id, {"kind": "approval_resolved", "via": "mcp_tool"})
        log_audit_event("AGENT_APPROVED", {"goal_id": goal_id})
        return {
            **_summarize_goal(goal),
            "ok": True,
            "message": "Approval granted. agent_goal_start will resume.",
        }
    except Exception as e:
        return format_error_response(e)


@mcp.tool(
    name="agent_reject",
    description="Reject a pending risky action and cancel the goal.",
)
def agent_reject(goal_id: str) -> dict:
    try:
        from app import event_bus
        goal = _load_goal(goal_id)
        event_bus.resolve_approval(goal_id, approved=False)
        goal["status"] = "cancelled"
        _save_goal(goal)
        _append_event(goal_id, {"kind": "approval_rejected", "via": "mcp_tool"})
        log_audit_event("AGENT_REJECTED", {"goal_id": goal_id})
        return {**_summarize_goal(goal), "ok": True, "message": "Goal cancelled."}
    except Exception as e:
        return format_error_response(e)
