from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Mapping


@dataclass
class CommandResult:
    command: str
    cwd: str
    exit_code: int
    started_at: str
    ended_at: str
    duration_sec: float
    stdout_path: str
    stderr_path: str
    combined_path: str
    combined_sha256: str


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def run_command(
    command: str,
    log_dir: Path,
    label: str,
    env: Mapping[str, str] | None = None,
    cwd: str | os.PathLike[str] | None = None,
    timeout: int | None = None,
    check: bool = False,
) -> CommandResult:
    log_dir.mkdir(parents=True, exist_ok=True)
    safe_label = "".join(c if c.isalnum() or c in "-_." else "-" for c in label).strip("-") or "cmd"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    stdout_path = log_dir / f"{stamp}-{safe_label}.stdout.log"
    stderr_path = log_dir / f"{stamp}-{safe_label}.stderr.log"
    combined_path = log_dir / f"{stamp}-{safe_label}.combined.log"

    merged_env = os.environ.copy()
    if env:
        merged_env.update({str(k): str(v) for k, v in env.items()})

    start_monotonic = time.monotonic()
    started_at = utc_now()
    with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=str(cwd or Path.cwd()),
            env=merged_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            stderr += f"\n[ctfh] TIMEOUT after {timeout}s\n".encode()
        out.write(stdout)
        err.write(stderr)

    with combined_path.open("wb") as combined:
        combined.write(b"$ ")
        combined.write(command.encode("utf-8", errors="replace"))
        combined.write(b"\n\n--- stdout ---\n")
        combined.write(stdout_path.read_bytes())
        combined.write(b"\n--- stderr ---\n")
        combined.write(stderr_path.read_bytes())

    ended_at = utc_now()
    result = CommandResult(
        command=command,
        cwd=str(cwd or Path.cwd()),
        exit_code=proc.returncode,
        started_at=started_at,
        ended_at=ended_at,
        duration_sec=round(time.monotonic() - start_monotonic, 3),
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        combined_path=str(combined_path),
        combined_sha256=sha256_file(combined_path),
    )
    meta_path = log_dir / f"{stamp}-{safe_label}.json"
    meta_path.write_text(json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8")
    if check and result.exit_code != 0:
        raise subprocess.CalledProcessError(result.exit_code, command)
    return result


def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
