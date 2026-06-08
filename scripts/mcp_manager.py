#!/usr/bin/env python3
"""Local management helper for the botquanganh_mcp server.

This script is intentionally dependency-light so it can run before the project
venv is fully healthy. It inspects the local host, Docker images, tunnel logs,
and MCP capability metadata, then prints operator-friendly status.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
LOGS_DIR = ROOT / "logs"
SERVER_LOG = LOGS_DIR / "server.log"
CLOUDFLARED_LOG = LOGS_DIR / "cloudflared.log"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"

DEFAULT_IMAGES = [
    "ctf-python-runner:latest",
    "ctf-pwn-runner:latest",
    "ctf-sage-runner:latest",
    "ctf-forensics-runner:latest",
]

HOST_COMMANDS = [
    ("sh", "POSIX shell"),
    ("bash", "Bash shell"),
    ("zsh", "Z shell"),
    ("ls", "List directory contents"),
    ("cat", "Print files"),
    ("head", "Print file start"),
    ("tail", "Print file end / follow logs"),
    ("less", "Pager"),
    ("sed", "Stream editor"),
    ("awk", "Text processing"),
    ("grep", "Text search"),
    ("rg", "Fast text search"),
    ("find", "Find files"),
    ("xargs", "Build command arguments"),
    ("sort", "Sort text"),
    ("uniq", "Unique lines"),
    ("cut", "Extract columns"),
    ("tr", "Translate/delete chars"),
    ("wc", "Count lines/words/bytes"),
    ("tee", "Write stdout to files"),
    ("xxd", "Hex dump"),
    ("hexdump", "Hex dump"),
    ("base64", "Base64 encode/decode"),
    ("sha256sum", "SHA256 hashing"),
    ("tar", "Tar archives"),
    ("unzip", "Zip extraction"),
    ("zip", "Zip creation"),
    ("gzip", "Gzip compression"),
    ("make", "Build automation"),
    ("python3", "Python runtime"),
    ("pip", "Python package installer"),
    ("git", "Git CLI"),
    ("gh", "GitHub CLI"),
    ("cloudflared", "Cloudflare tunnel"),
    ("docker", "Docker CLI"),
    ("curl", "HTTP client"),
    ("jq", "JSON helper"),
    ("nc", "Netcat"),
    ("ncat", "Ncat with SSL support"),
    ("file", "File type identification"),
    ("gdb", "Debugger for pwn/reverse"),
    ("sage", "SageMath crypto environment"),
    ("tshark", "PCAP analysis"),
    ("binwalk", "Firmware/file extraction"),
    ("exiftool", "Metadata extraction"),
    ("ffmpeg", "Audio/video conversion"),
    ("zsteg", "PNG/BMP stego"),
    ("volatility3", "Memory forensics"),
    ("rizin", "Reverse engineering"),
    ("radare2", "Reverse engineering"),
]

COMMAND_GROUPS = {
    "shell": [
        "sh",
        "bash",
        "zsh",
        "ls",
        "cat",
        "head",
        "tail",
        "less",
        "sed",
        "awk",
        "grep",
        "rg",
        "find",
        "xargs",
        "sort",
        "uniq",
        "cut",
        "tr",
        "wc",
        "tee",
    ],
    "files": [
        "file",
        "xxd",
        "hexdump",
        "base64",
        "sha256sum",
        "tar",
        "unzip",
        "zip",
        "gzip",
        "binwalk",
        "exiftool",
    ],
    "dev": [
        "python3",
        "pip",
        "git",
        "gh",
        "make",
        "docker",
        "jq",
    ],
    "network": [
        "curl",
        "nc",
        "ncat",
        "nmap",
        "openssl",
        "cloudflared",
        "tshark",
        "tcpdump",
    ],
    "ctf": [
        "gdb",
        "strace",
        "ltrace",
        "sage",
        "radare2",
        "rizin",
        "r2",
        "checksec",
        "ROPgadget",
        "ropper",
        "rp++",
        "one_gadget",
        "seccomp-tools",
        "patchelf",
        "pwninit",
        "msfvenom",
        "ghidraRun",
        "cutter",
        "ida64",
        "binaryninja",
        "zeratool",
        "pwnpasi",
        "autopwn",
        "liveexploit",
        "bloodfang",
        "koshary",
        "zsteg",
        "steghide",
        "volatility3",
        "ffmpeg",
    ],
    "web": [
        "curl",
        "httpx",
        "whatweb",
        "wappalyzer",
        "webanalyze",
        "ffuf",
        "feroxbuster",
        "gobuster",
        "dirb",
        "dirsearch",
        "arjun",
        "paramspider",
        "nuclei",
        "sqlmap",
        "xsstrike",
        "commix",
        "tplmap",
        "ssrfmap",
        "subfinder",
        "amass",
        "assetfinder",
        "massdns",
        "gowitness",
        "eyewitness",
        "playwright",
    ],
    "crypto": [
        "sage",
        "openssl",
        "z3",
        "RsaCtfTool",
        "rsatool",
        "ciphey",
        "katana",
        "hashcat",
        "john",
        "padbuster",
        "poracle",
        "hash_extender",
        "base64",
        "xxd",
    ],
    "forensics": [
        "file",
        "exiftool",
        "binwalk",
        "foremost",
        "scalpel",
        "photorec",
        "testdisk",
        "zsteg",
        "steghide",
        "stegoveritas",
        "stegsolve",
        "volatility3",
        "tshark",
        "tcpdump",
        "zeek",
        "ffmpeg",
        "identify",
        "usbrip",
    ],
    "reverse": [
        "file",
        "strings",
        "readelf",
        "objdump",
        "nm",
        "rizin",
        "radare2",
        "r2",
        "ghidraRun",
        "cutter",
        "ida64",
        "binaryninja",
        "angr",
        "qiling",
        "triton",
        "manticore",
        "unicorn",
        "qemu-x86_64",
        "de4dot",
        "jadx",
        "apktool",
    ],
}

COMMAND_ALIASES = {
    "volatility3": ["volatility3", "vol"],
    "stegsolve": ["stegsolve", "StegSolve.jar"],
}

PYTHON_MODULES = [
    ("requests", "requests"),
    ("bs4", "beautifulsoup4"),
    ("lxml", "lxml"),
    ("pwn", "pwntools"),
    ("Crypto", "pycryptodome"),
    ("z3", "z3-solver"),
    ("sympy", "sympy"),
    ("gmpy2", "gmpy2"),
    ("websocket", "websocket-client"),
    ("websockets", "websockets"),
    ("angr", "angr"),
    ("qiling", "qiling"),
    ("triton", "triton"),
    ("unicorn", "unicorn"),
    ("capstone", "capstone"),
    ("PIL", "Pillow"),
    ("scapy", "scapy"),
    ("httpx", "httpx"),
    ("playwright", "playwright"),
]


def run(
    args: list[str],
    *,
    check: bool = False,
    timeout: int = 8,
    cwd: Path = ROOT,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
        timeout=timeout,
    )


def read_env(path: Path = ENV_PATH) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        env[key.strip()] = os.path.expandvars(value)
    return env


def env_bool(env: dict[str, str], key: str, default: bool = False) -> bool:
    raw = env.get(key)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def ok_mark(value: bool) -> str:
    return "[OK]" if value else "[!!]"


def info_mark(value: bool) -> str:
    return "[on]" if value else "[off]"


def print_section(title: str) -> None:
    print(f"\n== {title} ==")


def conda_roots(env: dict[str, str] | None = None) -> list[Path]:
    env = env or read_env()
    roots: list[Path] = []
    for value in (
        env.get("MINIFORGE_PATH", ""),
        os.environ.get("MINIFORGE_PATH", ""),
        str(Path.home() / "miniforge3"),
        str(Path.home() / "mambaforge"),
        str(Path.home() / "anaconda3"),
        str(Path.home() / "miniconda3"),
    ):
        if not value:
            continue
        path = Path(value).expanduser()
        if path.exists() and path not in roots:
            roots.append(path)
    return roots


def conda_command_path(name: str, env: dict[str, str] | None = None) -> tuple[str, str]:
    for root in conda_roots(env):
        candidates = [
            (root / "bin" / name, "conda base"),
            (root / "condabin" / name, "condabin"),
        ]
        envs_dir = root / "envs"
        if envs_dir.exists():
            for env_dir in sorted(p for p in envs_dir.iterdir() if p.is_dir()):
                candidates.append((env_dir / "bin" / name, f"conda env: {env_dir.name}"))
        for path, source in candidates:
            if path.exists() and os.access(path, os.X_OK):
                return str(path), source
    return "", ""


def extra_bin_dirs(env: dict[str, str] | None = None) -> list[tuple[Path, str]]:
    env = env or read_env()
    dirs: list[tuple[Path, str]] = [
        (ROOT / ".venv" / "bin", "project venv"),
        (Path.home() / ".local" / "bin", "user local"),
    ]
    gem_user_bin = Path.home() / ".local" / "share" / "gem" / "ruby" / "3.3.0" / "bin"
    dirs.append((gem_user_bin, "user gem"))
    gem_home = env.get("GEM_HOME", "") or os.environ.get("GEM_HOME", "")
    if gem_home:
        dirs.append((Path(gem_home).expanduser() / "bin", "GEM_HOME"))
    return dirs


def find_extra_command(name: str, env: dict[str, str] | None = None) -> tuple[str, str]:
    for directory, source in extra_bin_dirs(env):
        path = directory / name
        if path.exists() and os.access(path, os.X_OK):
            return str(path), source
    return "", ""


def candidate_command_names(name: str) -> list[str]:
    return COMMAND_ALIASES.get(name, [name])


def command_path(name: str, env: dict[str, str] | None = None) -> str:
    path, _source = command_source(name, env)
    return path


def command_source(name: str, env: dict[str, str] | None = None) -> tuple[str, str]:
    for candidate in candidate_command_names(name):
        path = shutil.which(candidate)
        if path:
            source = "PATH" if candidate == name else f"PATH alias: {candidate}"
            return path, source
        path, source = find_extra_command(candidate, env)
        if path:
            if candidate != name:
                source = f"{source} alias: {candidate}"
            return path, source
        path, source = conda_command_path(candidate, env)
        if path:
            if candidate != name:
                source = f"{source} alias: {candidate}"
            return path, source
    return "", ""


def command_exists(name: str, env: dict[str, str] | None = None) -> bool:
    return bool(command_path(name, env))


def port_pids(port: int) -> list[str]:
    if not command_exists("lsof"):
        return []
    proc = run(["lsof", "-t", "-i", f":{port}"], timeout=4)
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def pgrep(pattern: str) -> list[str]:
    if not command_exists("pgrep"):
        return []
    proc = run(["pgrep", "-f", pattern], timeout=4)
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def socket_alive(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_probe(host: str, port: int, path: str) -> tuple[bool, str]:
    url = f"http://{host}:{port}{path}"
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=2) as response:
            return True, f"HTTP {response.status}"
    except HTTPError as exc:
        # MCP endpoints often reject plain GET while still being alive.
        if exc.code in {400, 404, 405, 406}:
            return True, f"HTTP {exc.code} (route alive)"
        return False, f"HTTP {exc.code}"
    except URLError as exc:
        return False, str(exc.reason)
    except Exception as exc:  # noqa: BLE001 - operator diagnostic script
        return False, str(exc)


def latest_tunnel_url() -> str:
    if not CLOUDFLARED_LOG.exists():
        return ""
    text = CLOUDFLARED_LOG.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", text)
    return matches[-1] if matches else ""


def docker_available() -> tuple[bool, str]:
    if not command_exists("docker"):
        return False, "docker CLI missing"
    proc = run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=8)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout).strip() or "docker daemon unavailable"
        return False, msg
    return True, proc.stdout.strip()


def docker_image_exists(image: str) -> bool:
    if not command_exists("docker"):
        return False
    proc = run(["docker", "image", "inspect", image], timeout=8)
    return proc.returncode == 0


def load_capabilities() -> dict:
    if not VENV_PYTHON.exists():
        return {"ok": False, "error": f"venv python missing: {VENV_PYTHON}"}
    code = (
        "import json;"
        "from app.tools.health import get_capabilities;"
        "print(json.dumps(get_capabilities(), sort_keys=True))"
    )
    proc = run([str(VENV_PYTHON), "-c", code], timeout=10)
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout).strip()}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"invalid capability JSON: {exc}", "raw": proc.stdout}


def check_python_module(python_bin: Path, module: str) -> bool:
    if not python_bin.exists():
        return False
    proc = run([str(python_bin), "-c", f"import {module}"], timeout=8)
    return proc.returncode == 0


def configured_images(env: dict[str, str]) -> list[str]:
    return [
        env.get("RUNNER_IMAGE_PYTHON", DEFAULT_IMAGES[0]),
        env.get("RUNNER_IMAGE_PWN", DEFAULT_IMAGES[1]),
        env.get("RUNNER_IMAGE_SAGE", DEFAULT_IMAGES[2]),
        env.get("RUNNER_IMAGE_FORENSICS", DEFAULT_IMAGES[3]),
    ]


def print_env_summary(env: dict[str, str]) -> None:
    print_section("Config")
    values = {
        "MCP_HOST": env.get("MCP_HOST", "127.0.0.1"),
        "MCP_PORT": env.get("MCP_PORT", "8000"),
        "MCP_PATH": env.get("MCP_PATH", "/mcp"),
        "ENABLE_ADVANCED_TOOLS": str(env_bool(env, "ENABLE_ADVANCED_TOOLS")),
        "ENABLE_AGENT_TOOLS": str(env_bool(env, "ENABLE_AGENT_TOOLS", True)),
        "ENABLE_WORKSPACE_TOOLS": str(env_bool(env, "ENABLE_WORKSPACE_TOOLS")),
        "AGENT_WORKSPACE_DIR": env.get("AGENT_WORKSPACE_DIR", "~/Workspace or repo root"),
        "ALLOWED_TCP_TARGETS": env.get("ALLOWED_TCP_TARGETS", ""),
        "BLOCK_PRIVATE_IPS": str(env_bool(env, "BLOCK_PRIVATE_IPS", True)),
    }
    for key, value in values.items():
        print(f"{key:24} {value}")


def print_process_status(env: dict[str, str]) -> None:
    host = env.get("MCP_HOST", "127.0.0.1")
    port = int(env.get("MCP_PORT", "8000"))
    path = env.get("MCP_PATH", "/mcp")
    pids = port_pids(port)
    cloudflared_pids = pgrep(rf"cloudflared tunnel --url http://.*:{port}")
    alive = socket_alive(host, port) or (host == "127.0.0.1" and socket_alive("localhost", port))
    http_ok, http_msg = http_probe(host, port, path) if alive else (False, "socket closed")
    tunnel_url = latest_tunnel_url()

    print_section("Server / Tunnel")
    print(f"{ok_mark(alive)} MCP socket        {host}:{port} pids={','.join(pids) if pids else '-'}")
    print(f"{ok_mark(http_ok)} MCP route         {path} {http_msg}")
    print(
        f"{ok_mark(bool(cloudflared_pids))} cloudflared      "
        f"pids={','.join(cloudflared_pids) if cloudflared_pids else '-'}"
    )
    if tunnel_url:
        mark = "[OK]" if cloudflared_pids else "[..]"
        print(f"{mark} last endpoint     {tunnel_url}{path}")
    else:
        print("[!!] public endpoint   not found in logs/cloudflared.log")


def print_capabilities() -> None:
    caps = load_capabilities()
    print_section("MCP Tools")
    if not caps.get("ok"):
        print(f"[!!] Could not load capabilities: {caps.get('error', 'unknown error')}")
        return
    print(f"profile              {caps.get('tool_profile')}")
    print(f"advanced_tools       {info_mark(bool(caps.get('advanced_tools_enabled')))}")
    print(f"agent_tools          {info_mark(bool(caps.get('agent_tools_enabled')))}")
    print(f"workspace_tools      {info_mark(bool(caps.get('workspace_tools_enabled')))}")

    for group in ("core_tools", "advanced_tools", "workspace_tools", "agent_tools"):
        tools = caps.get(group, [])
        if not tools:
            print(f"{group:20} -")
            continue
        print(f"{group:20} {len(tools)}")
        for tool in tools:
            print(f"  - {tool}")


def print_host_tools(env: dict[str, str] | None = None) -> None:
    print_section("Host Tools")
    for name, description in HOST_COMMANDS:
        path, source = command_source(name, env)
        source_note = f" ({source})" if source and source != "PATH" else ""
        print(f"{ok_mark(bool(path))} {name:12} {path or 'missing':35} {description}{source_note}")

    print_section("Python Packages (.venv)")
    for module, package in PYTHON_MODULES:
        installed = check_python_module(VENV_PYTHON, module)
        print(f"{ok_mark(installed)} {package:20} import {module}")


def print_command_palette(group_filter: str = "", env: dict[str, str] | None = None) -> None:
    print_section("Command Palette")
    groups = COMMAND_GROUPS
    if group_filter:
        groups = {group_filter: COMMAND_GROUPS.get(group_filter, [])}
    for group, names in groups.items():
        if not names:
            print(f"[!!] Unknown command group: {group}")
            continue
        print(f"{group}:")
        for name in names:
            path, source = command_source(name, env)
            status = "available" if path else "missing"
            source_note = f" ({source})" if source and source != "PATH" else ""
            print(f"  {ok_mark(bool(path))} {name:14} {status:9} {path or '-'}{source_note}")


def print_docker_images(env: dict[str, str]) -> None:
    available, detail = docker_available()
    print_section("Docker")
    print(f"{ok_mark(available)} daemon            {detail}")
    for image in configured_images(env):
        exists = docker_image_exists(image) if available else False
        print(f"{ok_mark(exists)} image             {image}")


def print_log_summary() -> None:
    print_section("Logs")
    for path in (SERVER_LOG, CLOUDFLARED_LOG, ROOT / "logs" / "gateway.log"):
        if path.exists():
            print(f"[OK] {path.relative_to(ROOT)} size={path.stat().st_size} bytes")
        else:
            print(f"[!!] {path.relative_to(ROOT)} missing")


def tail_file(path: Path, lines: int) -> None:
    if not path.exists():
        print(f"Missing log file: {path}")
        return
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in content[-lines:]:
        print(line)


def cmd_status(args: argparse.Namespace) -> int:
    env = read_env()
    print(f"botquanganh_mcp manager: {ROOT}")
    print_env_summary(env)
    print_process_status(env)
    print_capabilities()
    print_log_summary()
    if args.verbose:
        print_host_tools(env)
        print_docker_images(env)
    print_next_actions(env)
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    env = read_env()
    print(f"botquanganh_mcp doctor: {ROOT}")
    print_env_summary(env)
    print_process_status(env)
    print_capabilities()
    print_host_tools(env)
    print_docker_images(env)
    print_log_summary()
    print_next_actions(env)
    return 0


def cmd_tools(_args: argparse.Namespace) -> int:
    env = read_env()
    print_capabilities()
    print_command_palette(env=env)
    print_host_tools(env)
    return 0


def cmd_commands(args: argparse.Namespace) -> int:
    print_command_palette(args.group, read_env())
    return 0


def cmd_images(_args: argparse.Namespace) -> int:
    print_docker_images(read_env())
    return 0


def cmd_env(_args: argparse.Namespace) -> int:
    print_env_summary(read_env())
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    target = {
        "server": SERVER_LOG,
        "tunnel": CLOUDFLARED_LOG,
        "gateway": LOGS_DIR / "gateway.log",
    }[args.log]
    tail_file(target, args.lines)
    return 0


def stream_command(command: list[str]) -> int:
    proc = subprocess.Popen(command, cwd=str(ROOT))
    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        return proc.wait()


def cmd_start(_args: argparse.Namespace) -> int:
    return stream_command(["bash", str(ROOT / "scripts" / "start_tunnel_server.sh")])


def cmd_restart(_args: argparse.Namespace) -> int:
    return stream_command(["bash", str(ROOT / "scripts" / "restart_server_only.sh")])


def cmd_install_basic(_args: argparse.Namespace) -> int:
    return stream_command(["bash", str(ROOT / "scripts" / "install_basic.sh")])


def cmd_install_advanced(_args: argparse.Namespace) -> int:
    return stream_command(["bash", str(ROOT / "scripts" / "install_advanced_tools.sh")])


def print_next_actions(env: dict[str, str]) -> None:
    port = int(env.get("MCP_PORT", "8000"))
    pids = port_pids(port)
    tunnel_pids = pgrep(rf"cloudflared tunnel --url http://.*:{port}")
    print_section("Next Actions")
    if not pids:
        print("Start server+tunnel:  ./scripts/mcp_manager.py start")
    elif not tunnel_pids:
        print("Tunnel missing:       ./scripts/start_tunnel_server.sh")
    else:
        print("Restart server only:  ./scripts/mcp_manager.py restart")
    print("Full doctor:          ./scripts/mcp_manager.py doctor")
    print("Tail server log:      ./scripts/mcp_manager.py logs server")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage and inspect the local botquanganh_mcp server, tunnel, tools, and Docker images."
    )
    sub = parser.add_subparsers(dest="command", required=False)

    status = sub.add_parser("status", help="Show concise server, tunnel, capability, and log status.")
    status.add_argument("-v", "--verbose", action="store_true", help="Also show host tools and Docker images.")
    status.set_defaults(func=cmd_status)

    doctor = sub.add_parser("doctor", help="Run the full local environment report.")
    doctor.set_defaults(func=cmd_doctor)

    tools = sub.add_parser("tools", help="Show MCP tool capabilities and host Python packages.")
    tools.set_defaults(func=cmd_tools)

    commands = sub.add_parser("commands", help="Show common shell/CTF commands available on this host.")
    commands.add_argument(
        "group",
        choices=["", *COMMAND_GROUPS.keys()],
        nargs="?",
        default="",
        help="Optional command group to show.",
    )
    commands.set_defaults(func=cmd_commands)

    images = sub.add_parser("images", help="Show Docker daemon and runner image status.")
    images.set_defaults(func=cmd_images)

    env = sub.add_parser("env", help="Show important .env values.")
    env.set_defaults(func=cmd_env)

    logs = sub.add_parser("logs", help="Tail one of the MCP logs.")
    logs.add_argument("log", choices=["server", "tunnel", "gateway"], nargs="?", default="server")
    logs.add_argument("-n", "--lines", type=int, default=80)
    logs.set_defaults(func=cmd_logs)

    start = sub.add_parser("start", help="Start MCP server with Cloudflare tunnel.")
    start.set_defaults(func=cmd_start)

    restart = sub.add_parser("restart", help="Restart only the local MCP server process.")
    restart.set_defaults(func=cmd_restart)

    install_basic = sub.add_parser("install-basic", help="Run scripts/install_basic.sh.")
    install_basic.set_defaults(func=cmd_install_basic)

    install_advanced = sub.add_parser("install-advanced", help="Run scripts/install_advanced_tools.sh.")
    install_advanced.set_defaults(func=cmd_install_advanced)

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not hasattr(args, "func"):
        args = parser.parse_args(["status"])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
