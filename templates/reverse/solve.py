#!/usr/bin/env python3
"""CTF Harness — REVERSE solver template."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from ctfharness.constants import FLAG_REGEX_DEFAULT

FLAG_RE_B = re.compile(FLAG_REGEX_DEFAULT.encode())


def run(cmd: list[str]) -> bytes:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=20)
    except Exception as exc:
        print(f"[!] {' '.join(cmd)} failed: {exc}")
        return b""


def scan(data: bytes) -> str | None:
    hit = FLAG_RE_B.search(data)
    return hit.group(0).decode(errors="replace") if hit else None


def solve(path: Path) -> str | None:
    if not path.exists():
        print(f"[-] missing file: {path}", file=sys.stderr)
        return None
    hit = scan(path.read_bytes()[:50_000_000])
    if hit:
        return hit
    for cmd in [["strings", "-a", str(path)], ["file", str(path)], ["objdump", "-d", str(path)]]:
        out = run(cmd)
        print(out[:5000].decode(errors="replace"))
        hit = scan(out)
        if hit:
            return hit
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("binary", nargs="?", default="artifacts/binary")
    args = ap.parse_args()
    flag = solve(Path(args.binary))
    if flag:
        print(f"FLAG={flag}")
        return 0
    print("[-] no flag found yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
