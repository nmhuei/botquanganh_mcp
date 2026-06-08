from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .logging_utils import run_command, sha256_file, utc_now


@dataclass
class FlagFinding:
    flag: str
    source_file: str
    source_sha256: str
    context: str
    mode: str
    status: str
    reason: str


_BINARY_SUFFIXES = {
    ".zip", ".gz", ".tar", ".bz2", ".xz", ".7z", ".rar",
    ".so", ".o", ".a", ".elf", ".exe", ".dll", ".pyc",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".pdf", ".mp4", ".mp3", ".wav", ".avi", ".mkv",
    ".db", ".sqlite", ".sqlite3",
}


def iter_text_files(root: Path, max_bytes: int = 5_000_000) -> Iterable[Path]:
    if not root.exists():
        return []
    candidates: list[Path] = []
    if root.is_file():
        roots = [root]
    else:
        roots = list(root.rglob("*"))
    for p in roots:
        if not p.is_file():
            continue
        if p.suffix.lower() in _BINARY_SUFFIXES:
            continue
        try:
            if p.stat().st_size > max_bytes:
                continue
        except OSError:
            continue
        if any(part in {".git", "__pycache__", ".venv", "node_modules"} for part in p.parts):
            continue
        candidates.append(p)
    return candidates


def detect_flags(root: Path, flag_regex: str, mode: str, reject_words: list[str]) -> list[FlagFinding]:
    rx = re.compile(flag_regex)
    findings: list[FlagFinding] = []
    seen: set[tuple[str, str]] = set()

    for p in iter_text_files(root):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in rx.finditer(text):
            flag = m.group(0)
            key = (flag, str(p))
            if key in seen:
                continue
            seen.add(key)
            lo = max(0, m.start() - 160)
            hi = min(len(text), m.end() + 160)
            context = text[lo:hi].replace("\x00", "")
            lower_flag = flag.lower()
            decoy_hit = [w for w in reject_words if w.lower() in lower_flag]
            if decoy_hit:
                status = "suspect-decoy"
                reason = f"matched reject words: {', '.join(decoy_hit)}"
            elif mode == "remote":
                status = "candidate"
                reason = "flag-like token found in remote artifact; run verifier to confirm"
            else:
                status = "candidate-local"
                reason = "flag-like token found only in local artifact"
            findings.append(
                FlagFinding(
                    flag=flag,
                    source_file=str(p),
                    source_sha256=sha256_file(p),
                    context=context,
                    mode=mode,
                    status=status,
                    reason=reason,
                )
            )
    return findings


def write_evidence(
    out_path: Path,
    findings: list[FlagFinding],
    mode: str,
    target: str,
    verifier_command: str | None = None,
    log_dir: Path | None = None,
) -> dict:
    verified = []
    verifier_results = []

    for finding in findings:
        status = finding.status
        reason = finding.reason
        if verifier_command and finding.status not in {"suspect-decoy"}:
            env = {"FLAG": finding.flag, "MODE": mode, "TARGET": target}
            result = run_command(
                verifier_command,
                log_dir or out_path.parent,
                f"verify-{mode}",
                env=env,
                check=False,
            )
            verifier_results.append(result.__dict__)
            if result.exit_code == 0:
                status = "verified"
                reason = "verifier command exited 0; platform/checker accepted the flag"
            else:
                status = "candidate"
                reason = f"verifier command exited {result.exit_code}; flag not confirmed"

        verified.append({**asdict(finding), "status": status, "reason": reason})

    evidence = {
        "created_at": utc_now(),
        "mode": mode,
        "target": target,
        "status": "no-flag" if not verified else max((x["status"] for x in verified), key=_rank),
        "findings": verified,
        "verifier_results": verifier_results,
        "note": (
            "candidate = regex match only. verified = explicit verifier command exited 0. "
            "Remote transcripts are evidence, but they are not auto-upgraded to verified."
        ),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    return evidence


def _rank(status: str) -> int:
    return {
        "no-flag": 0,
        "suspect-decoy": 1,
        "candidate-local": 2,
        "candidate": 3,
        "verified": 4,
    }.get(status, 0)
