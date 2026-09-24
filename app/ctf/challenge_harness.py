"""Automated CTF challenge scaffolding, file downloading, and harness setup.

Enforces workspace discipline:
- challenge/: Read-only original challenge artifacts and NOTE.md
- script/: Probes, scratch harnesses, and living analysis.md
- solver/: Standalone, reproducible final solve.py
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tarfile
from typing import Any, Optional
from urllib.parse import unquote, urlparse
import zipfile

import httpx

from app.ctf.triage import triage_artifact


MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024  # 50 MB safety cap
DOWNLOAD_TIMEOUT_SECONDS = 30.0

VALID_CATEGORIES = frozenset({"pwn", "reverse", "crypto", "web", "forensics", "misc", "ai-ml", "osint"})


_SOLVER_TEMPLATES: dict[str, str] = {
    "pwn": '''#!/usr/bin/env python3
"""Deterministic exploit script for {name} ({category})."""

import os
import sys
from pwn import *

HOST = "{target_host}"
PORT = {target_port}
BINARY = "../challenge/{binary_name}"

context.terminal = ['tmux', 'splitw', '-h']
if os.path.exists(BINARY):
    elf = context.binary = ELF(BINARY, checksec=True)

def start():
    if args.REMOTE:
        if not HOST or not PORT:
            log.error("HOST and PORT must be defined for REMOTE exploitation.")
        return remote(HOST, PORT)
    return process([BINARY])

def exploit():
    io = start()
    log.info("Starting exploit harness...")

    # === [PHASE 1: LEAK / RECON] ===

    # === [PHASE 2: PAYLOAD DISPATCH] ===

    # === [PHASE 3: INTERACTIVE / FLAG RECOVERY] ===
    io.interactive()

if __name__ == "__main__":
    exploit()
''',

    "crypto": '''#!/usr/bin/env python3
"""Deterministic cryptographic solver for {name} ({category})."""

import sys
# from Crypto.Util.number import *
# from sympy import *

def solve():
    print("[*] Loading challenge parameters...")
    # === [SOLVER LOGIC HERE] ===

    flag = "FLAG{{placeholder}}"
    print(f"[+] Recovered flag: {flag}")
    return flag

if __name__ == "__main__":
    solve()
''',

    "web": '''#!/usr/bin/env python3
"""Deterministic web exploit harness for {name} ({category})."""

import requests
import sys

TARGET_URL = "{target_url}"
session = requests.Session()

def exploit():
    print(f"[*] Attacking endpoint: {TARGET_URL}")
    # === [WEB EXPLOIT / INJECTION LOGIC HERE] ===

if __name__ == "__main__":
    exploit()
''',

    "reverse": '''#!/usr/bin/env python3
"""Reverse engineering keygen / logic inverter for {name} ({category})."""

import sys
# from z3 import *

def solve():
    print("[*] Initializing constraint solver / logic inversion...")
    # === [INVERSION / Z3 LOGIC HERE] ===

if __name__ == "__main__":
    solve()
''',

    "default": '''#!/usr/bin/env python3
"""Deterministic solver for {name} ({category})."""

import sys

def solve():
    print("[*] Running {name} solver...")
    # === [SOLVE LOGIC HERE] ===

if __name__ == "__main__":
    solve()
''',
}


def _safe_extract_zip(archive_path: Path, dest_dir: Path) -> list[str]:
    """Safely extract a ZIP archive rejecting any path traversal entries."""
    extracted = []
    dest_resolved = dest_dir.resolve()
    with zipfile.ZipFile(archive_path, "r") as zf:
        for member in zf.infolist():
            filename = member.filename
            if filename.startswith("/") or ".." in filename.split("/"):
                continue
            target_path = (dest_dir / filename).resolve()
            try:
                target_path.relative_to(dest_resolved)
            except ValueError:
                continue
            zf.extract(member, dest_dir)
            extracted.append(filename)
    return extracted


def _safe_extract_tar(archive_path: Path, dest_dir: Path) -> list[str]:
    """Safely extract a TAR archive rejecting any path traversal entries."""
    extracted = []
    dest_resolved = dest_dir.resolve()
    with tarfile.open(archive_path, "r:*") as tf:
        for member in tf.getmembers():
            name = member.name
            if name.startswith("/") or ".." in name.split("/"):
                continue
            target_path = (dest_dir / name).resolve()
            try:
                target_path.relative_to(dest_resolved)
            except ValueError:
                continue
            try:
                tf.extract(member, dest_dir, filter="data")
            except TypeError:
                tf.extract(member, dest_dir)
            extracted.append(name)
    return extracted


def download_and_extract_challenge(
    url: str,
    challenge_dir: Path,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> tuple[Path, list[str]]:
    """Download a remote CTF challenge artifact and extract if it is an archive."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Download URL must use HTTP or HTTPS.")

    filename = Path(unquote(parsed.path)).name or "artifact.bin"
    target_file = challenge_dir / filename

    with httpx.Client(timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            content_disp = response.headers.get("content-disposition", "")
            match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', content_disp, re.IGNORECASE)
            if match:
                clean_name = Path(unquote(match.group(1).strip())).name
                if clean_name and not clean_name.startswith("."):
                    target_file = challenge_dir / clean_name

            downloaded = 0
            with open(target_file, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=65536):
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        raise ValueError(f"Download exceeded maximum size limit of {max_bytes} bytes.")
                    f.write(chunk)

    extracted_files: list[str] = [target_file.name]
    # Check if archive
    lower_name = target_file.name.lower()
    if lower_name.endswith(".zip"):
        unpacked = _safe_extract_zip(target_file, challenge_dir)
        extracted_files.extend(unpacked)
    elif lower_name.endswith((".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar")):
        unpacked = _safe_extract_tar(target_file, challenge_dir)
        extracted_files.extend(unpacked)

    return target_file, extracted_files


def setup_ctf_harness(
    workspace_dir: Path,
    name: str,
    category: str = "pwn",
    url: Optional[str] = None,
    description: Optional[str] = None,
    target: Optional[str] = None,
) -> dict[str, Any]:
    """Scaffold standard 3-folder CTF harness with boilerplate notes, analysis, and solver."""
    clean_name = re.sub(r"[^A-Za-z0-9_-]", "_", name.strip()) or "chal"
    norm_cat = category.strip().lower()
    if norm_cat not in VALID_CATEGORIES:
        norm_cat = "misc"

    ws = Path(workspace_dir).resolve()
    ws.mkdir(parents=True, exist_ok=True)

    challenge_dir = ws / "challenge"
    script_dir = ws / "script"
    probes_dir = script_dir / "probes"
    solver_dir = ws / "solver"

    challenge_dir.mkdir(parents=True, exist_ok=True)
    script_dir.mkdir(parents=True, exist_ok=True)
    probes_dir.mkdir(parents=True, exist_ok=True)
    solver_dir.mkdir(parents=True, exist_ok=True)

    # Parse target host / port if given (e.g. "challenge.example.com:1337" or "nc host port")
    target_host = ""
    target_port = 0
    target_url = target or url or ""
    if target:
        parts = target.strip().split()
        candidate = parts[-1] if len(parts) >= 2 else parts[0]
        if ":" in candidate:
            host_p, port_p = candidate.split(":", 1)
            target_host = host_p
            try:
                target_port = int(port_p)
            except ValueError:
                pass
        elif len(parts) >= 2 and parts[-1].isdigit():
            target_host = parts[-2]
            target_port = int(parts[-1])

    # 1. Download challenge file if url provided
    downloaded_files: list[str] = []
    primary_artifact: Optional[Path] = None
    if url:
        try:
            art_file, files = download_and_extract_challenge(url, challenge_dir)
            primary_artifact = art_file
            downloaded_files = files
        except Exception as exc:
            downloaded_files.append(f"download_failed: {exc}")

    # Look for primary binary in challenge dir if not set
    if primary_artifact is None or not primary_artifact.is_file():
        for candidate in challenge_dir.iterdir():
            if candidate.is_file() and not candidate.name.endswith((".md", ".txt", ".json", ".zip", ".tar.gz")):
                primary_artifact = candidate
                break

    binary_name = primary_artifact.name if primary_artifact else clean_name

    # 2. metadata.json
    meta = {
        "challenge_id": f"{norm_cat}_{clean_name}",
        "name": clean_name,
        "category": norm_cat,
        "target": target or "",
        "target_host": target_host,
        "target_port": target_port,
        "url": url or "",
        "status": "in_progress",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (ws / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # 3. challenge/NOTE.md
    note_content = f"""# Challenge: {clean_name}

- **Category:** {norm_cat.upper()}
- **Target Endpoint:** `{target or 'Local / Not specified'}`
- **Source URL:** {url or 'Not specified'}
- **Created At:** {meta['created_at']}

## Description
{description or 'Challenge description or initial prompt goes here.'}

## Hints & Author Notes
- Remember: NEVER submit flags automatically. Store candidate flags in `script/analysis.md`.
- Inspect artifacts in this directory with `ctf_triage_artifact`.
"""
    (challenge_dir / "NOTE.md").write_text(note_content, encoding="utf-8")

    # 4. Perform initial triage on primary artifact if found
    triage_info: Optional[dict[str, Any]] = None
    triage_summary = "*(No primary binary triaged yet. Run `ctf_triage_artifact` on challenge files.)*"
    if primary_artifact and primary_artifact.is_file() and not primary_artifact.name.endswith((".md", ".txt", ".json")):
        try:
            triage_info = triage_artifact(primary_artifact, calculate_entropy_flag=True, extract_strings_flag=True)
            if triage_info.get("ok"):
                arch = triage_info.get("architecture") or "unknown"
                fmt = triage_info.get("format") or "unknown"
                sec = triage_info.get("security_mitigations") or {}
                ent = triage_info.get("entropy") or {}
                triage_summary = f"""- **File:** `{primary_artifact.name}` ({fmt}, {arch})
- **Mitigations:** NX={sec.get('nx')}, PIE={sec.get('pie')}, Canary={sec.get('canary')}, RELRO={sec.get('relro')}, Stripped={sec.get('stripped')}
- **Entropy:** {ent.get('shannon_entropy', 'N/A')} bits/byte
"""
        except Exception:
            pass

    # 5. script/analysis.md (Living Analysis & Candidate Flags)
    analysis_content = f"""# Analysis: {clean_name}

## 1. Status & Phase
- **Current Phase:** TRIAGE
- **Category:** {norm_cat.upper()}

## 2. Artifact & Mitigations
{triage_summary}

## 3. Candidate Flags Lifecycle
| Candidate Flag | State (`CANDIDATE` / `VERIFIED` / `REJECTED`) | Discovery Source | Proof & Reproduction |
|---|---|---|---|
| *(No flags discovered yet)* | - | - | - |

## 4. Verified Facts
- [x] Challenge harness initialized with `challenge/`, `script/`, and `solver/`.

## 5. Working Hypotheses
- [ ] Hypothesis 1: ...

## 6. Dead Ends Eliminated
- *(None yet)*
"""
    (script_dir / "analysis.md").write_text(analysis_content, encoding="utf-8")

    # 6. solver/solve.py
    template_str = _SOLVER_TEMPLATES.get(norm_cat, _SOLVER_TEMPLATES["default"])
    solve_code = (
        template_str
        .replace("{name}", clean_name)
        .replace("{category}", norm_cat)
        .replace("{target_host}", target_host or "127.0.0.1")
        .replace("{target_port}", str(target_port or 1337))
        .replace("{target_url}", target_url or "http://127.0.0.1:8000")
        .replace("{binary_name}", binary_name)
    )

    solve_file = solver_dir / "solve.py"
    solve_file.write_text(solve_code, encoding="utf-8")
    try:
        os.chmod(solve_file, 0o755)
    except OSError:
        pass

    # 7. solver/requirements.txt
    reqs = ["requests\n"]
    if norm_cat == "pwn":
        reqs.append("pwntools\n")
    elif norm_cat == "crypto":
        reqs.extend(["pycryptodome\n", "sympy\n"])
    elif norm_cat == "reverse":
        reqs.append("z3-solver\n")
    (solver_dir / "requirements.txt").write_text("".join(reqs), encoding="utf-8")

    return {
        "ok": True,
        "name": clean_name,
        "category": norm_cat,
        "workspace_dir": str(ws),
        "harness": {
            "challenge_dir": str(challenge_dir),
            "script_dir": str(script_dir),
            "solver_dir": str(solver_dir),
            "note_file": str(challenge_dir / "NOTE.md"),
            "analysis_file": str(script_dir / "analysis.md"),
            "solver_file": str(solve_file),
        },
        "downloaded_files": downloaded_files,
        "triage": triage_info,
        "message": f"CTF harness created successfully for '{clean_name}' ({norm_cat}).",
    }
