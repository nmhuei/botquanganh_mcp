#!/usr/bin/env python3
"""CTF Harness — OSINT solver template."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from ctfharness.constants import FLAG_REGEX_DEFAULT

FLAG_RE = re.compile(FLAG_REGEX_DEFAULT)


def run(cmd: list[str]) -> str:
    print(f"[cmd] {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return r.stdout + r.stderr


def extract_flag(text: str) -> str | None:
    hit = FLAG_RE.search(text)
    return hit.group(0) if hit else None


def scan_files(root: Path) -> str | None:
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.stat().st_size > 20_000_000:
            continue
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".pdf", ".docx"}:
            try:
                hit = extract_flag(run(["exiftool", str(p)]))
                if hit:
                    return hit
            except Exception:
                pass
        try:
            hit = extract_flag(p.read_text(encoding="utf-8", errors="replace"))
            if hit:
                return hit
        except Exception:
            pass
    return None


def recon_domain(domain: str) -> str | None:
    outputs = []
    for cmd in (["whois", domain], ["dig", "+short", "TXT", domain], ["dig", "+short", "MX", domain], ["dig", "+short", "NS", domain]):
        try:
            outputs.append(run(cmd))
        except Exception as exc:
            outputs.append(str(exc))
    combined = "\n".join(outputs)
    print(combined[:3000])
    return extract_flag(combined)


def print_guide(target: str) -> None:
    print(f"""
OSINT guide for: {target}

- Check archives: https://web.archive.org/web/*/{target}
- Search exact strings/usernames on GitHub, Twitter/X, Reddit, LinkedIn.
- Domain: whois {target}; dig TXT/MX/NS {target}; certificate transparency.
- Images: reverse image search, EXIF, shadows, signs, terrain, architecture.
- Keep evidence URLs/screenshots and timestamps in workspaces/<challenge>/evidence/.
""")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="")
    ap.add_argument("--scan", default="artifacts")
    args = ap.parse_args()
    scan_root = Path(args.scan)
    if scan_root.exists():
        flag = scan_files(scan_root)
        if flag:
            print(f"FLAG={flag}")
            return 0
    if not args.target:
        print_guide("TARGET")
        print("[-] no target and no flag in local artifacts", file=sys.stderr)
        return 1
    if re.match(r"^[a-zA-Z0-9][a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", args.target):
        flag = recon_domain(args.target)
    else:
        print_guide(args.target)
        flag = None
    if flag:
        print(f"FLAG={flag}")
        return 0
    print("[-] no flag found yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
