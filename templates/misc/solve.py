#!/usr/bin/env python3
"""CTF Harness generic artifact scanner/template.
Challenge : __CHALLENGE__
Category  : misc
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from ctfharness.constants import FLAG_REGEX_DEFAULT

FLAG_RE_B = re.compile(FLAG_REGEX_DEFAULT.encode())


def scan_bytes(data: bytes) -> str | None:
    hit = FLAG_RE_B.search(data)
    return hit.group(0).decode(errors="replace") if hit else None


def scan_path(path: Path) -> str | None:
    if path.is_file():
        return scan_bytes(path.read_bytes()[:20_000_000])
    for p in sorted(path.rglob("*")):
        if not p.is_file() or p.stat().st_size > 20_000_000:
            continue
        hit = scan_bytes(p.read_bytes())
        if hit:
            print(f"[+] source={p}")
            return hit
    return None


def solve(args: argparse.Namespace) -> str | None:
    # TODO: replace with category-specific exploit/derivation.
    return scan_path(Path(args.path))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="artifacts")
    args = ap.parse_args()
    flag = solve(args)
    if flag:
        print(f"FLAG={flag}")
        return 0
    print("[-] no flag found yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
