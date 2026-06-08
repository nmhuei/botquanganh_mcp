#!/usr/bin/env python3
"""CTF Harness — FORENSICS solver template."""
from __future__ import annotations

import argparse
import base64
import codecs
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from ctfharness.constants import FLAG_REGEX_DEFAULT

FLAG_RE_B = re.compile(FLAG_REGEX_DEFAULT.encode())
FLAG_RE_S = re.compile(FLAG_REGEX_DEFAULT)
TRANSCRIPT: list[str] = []


def log(msg: str) -> None:
    print(msg)
    TRANSCRIPT.append(msg)


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    log(f"[cmd] {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True)


def scan_bytes(data: bytes) -> str | None:
    hit = FLAG_RE_B.search(data)
    return hit.group(0).decode(errors="replace") if hit else None


def scan_str(data: str) -> str | None:
    hit = FLAG_RE_S.search(data)
    return hit.group(0) if hit else None


def scan_encoded_layers(data: bytes) -> str | None:
    for decoder in (lambda b: base64.b64decode(b.strip()), lambda b: bytes.fromhex(b.strip().decode())):
        try:
            hit = scan_bytes(decoder(data))
            if hit:
                return hit
        except Exception:
            pass
    try:
        hit = scan_str(codecs.decode(data.decode(errors="replace"), "rot_13"))
        if hit:
            return hit
    except Exception:
        pass
    return None


def triage_file(p: Path) -> str | None:
    log(f"[triage] {p}")
    raw = p.read_bytes()
    for hit in (scan_bytes(raw), scan_encoded_layers(raw)):
        if hit:
            return hit
    file_out = run(["file", str(p)]).stdout.lower()
    log(file_out.strip())
    strings_out = run(["strings", "-a", str(p)]).stdout
    hit = scan_str(strings_out)
    if hit:
        return hit
    if ("zip" in file_out or p.suffix.lower() == ".zip") and p.stat().st_size < 50_000_000:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["unzip", "-q", "-o", str(p), "-d", tmp], capture_output=True)
            return scan_dir(Path(tmp))
    if any(x in file_out for x in ("png", "jpeg", "jpg", "pdf", "gif")):
        exif = subprocess.run(["exiftool", str(p)], capture_output=True, text=True)
        hit = scan_str(exif.stdout)
        if hit:
            return hit
    if "pcap" in file_out or p.suffix.lower() in {".pcap", ".pcapng"}:
        if subprocess.run(["which", "tshark"], capture_output=True).returncode == 0:
            out = run(["tshark", "-r", str(p), "-T", "fields", "-e", "data.text", "-e", "http.file_data"]).stdout
            return scan_str(out)
    return None


def scan_dir(root: Path) -> str | None:
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.stat().st_size <= 50_000_000:
            hit = triage_file(p)
            if hit:
                return hit
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="artifacts")
    args = ap.parse_args()
    target = Path(args.path)
    if not target.exists():
        print(f"[-] path not found: {target}", file=sys.stderr)
        return 2
    flag = triage_file(target) if target.is_file() else scan_dir(target)
    Path("transcript_forensics.txt").write_text("\n".join(TRANSCRIPT), encoding="utf-8")
    if flag:
        print(f"FLAG={flag}")
        return 0
    print("[-] no flag found yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
