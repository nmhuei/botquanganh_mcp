from __future__ import annotations

import re
import shutil
import subprocess  # nosec B404
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from app.cli.context import CLIContext
from app.cli.errors import CLIError, EXIT_USAGE, NotFoundCLIError
from app.cli.output import emit_json


LOG_FILES = {
    "server": "server.log",
    "tunnel": "cloudflared.log",
    "launcher": "launcher.log",
    "audit": "gateway.log",
}
_DURATION_RE = re.compile(r"^(\d+)([smhd])$")
_TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:[.,](\d+))?(Z|[+-]\d{2}:?\d{2})?")


def _duration(value: str) -> timedelta:
    match = _DURATION_RE.fullmatch(value.strip().lower())
    if not match:
        raise CLIError("--since must use a value such as 30s, 10m, 2h, or 1d.", EXIT_USAGE)
    amount = int(match.group(1))
    unit = match.group(2)
    return {
        "s": timedelta(seconds=amount),
        "m": timedelta(minutes=amount),
        "h": timedelta(hours=amount),
        "d": timedelta(days=amount),
    }[unit]


def _timestamp(line: str) -> datetime | None:
    match = _TIMESTAMP_RE.match(line)
    if not match:
        return None
    date, clock, fraction, zone = match.groups()
    text = f"{date}T{clock}"
    if fraction:
        text += f".{fraction[:6]}"
    if zone == "Z":
        text += "+00:00"
    elif zone:
        if len(zone) == 5 and ":" not in zone:
            zone = f"{zone[:3]}:{zone[3:]}"
        text += zone
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _filtered_lines(path: Path, *, lines: int, since: str | None, grep_text: str | None) -> list[str]:
    if not path.is_file():
        raise NotFoundCLIError(f"Log file not found: {path}")
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if since:
        cutoff = datetime.now(timezone.utc) - _duration(since)
        filtered: list[str] = []
        include_block = False
        for line in content:
            stamp = _timestamp(line)
            if stamp is not None:
                include_block = stamp >= cutoff
            if include_block:
                filtered.append(line)
        content = filtered
    if grep_text:
        content = [line for line in content if grep_text in line]
    if lines < 0:
        raise CLIError("--lines must be zero or greater.", EXIT_USAGE)
    return content[-lines:] if lines else []


def _paths(ctx: CLIContext, args) -> list[tuple[str, Path]]:
    if args.log_action == "follow":
        if args.all_logs:
            names = list(LOG_FILES)
        elif args.follow_target:
            names = [args.follow_target]
        else:
            raise CLIError("Use 'bqa logs follow <target>' or 'bqa logs follow --all'.", EXIT_USAGE)
    elif args.all_logs:
        names = list(LOG_FILES)
    else:
        names = [args.log_action]
    return [(name, ctx.repo_root / "logs" / LOG_FILES[name]) for name in names]


def _follow(paths: Iterable[tuple[str, Path]], lines: int, grep_text: str | None) -> int:
    selected = list(paths)
    for _, path in selected:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
    tail_path = shutil.which("tail")
    if not tail_path:
        raise CLIError("The system 'tail' command is required for follow mode.")
    process = subprocess.Popen(  # nosec B603
        [tail_path, "-n", str(lines), "-F", *[str(path) for _, path in selected]],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        if process.stdout is None:  # pragma: no cover
            raise CLIError("Unable to capture tail output.")
        for line in process.stdout:
            if grep_text and grep_text not in line:
                continue
            sys.stdout.write(line)
            sys.stdout.flush()
    except KeyboardInterrupt:
        process.terminate()
    finally:
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
    return 0


def handle_logs(ctx: CLIContext, args) -> int:
    paths = _paths(ctx, args)
    follow = args.follow or args.log_action == "follow"
    if follow:
        if ctx.json_output:
            raise CLIError("--json cannot be combined with log follow mode.", EXIT_USAGE)
        return _follow(paths, args.lines, args.grep_text)

    payload = []
    for name, path in paths:
        lines = _filtered_lines(path, lines=args.lines, since=args.since, grep_text=args.grep_text)
        payload.append({"name": name, "path": str(path), "lines": lines})
    if ctx.json_output:
        emit_json({"ok": True, "logs": payload})
        return 0
    for index, item in enumerate(payload):
        if len(payload) > 1:
            if index:
                print()
            print(f"===== {item['name']} ({item['path']}) =====")
        for line in item["lines"]:
            print(line)
    return 0
