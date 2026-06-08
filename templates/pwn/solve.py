#!/usr/bin/env python3
"""CTF Harness — PWN solver template.
Challenge : __CHALLENGE__
Remote    : __HOST__:__PORT__

Usage:
  python3 solve.py
  python3 solve.py GDB
  HOST=host PORT=1337 SSL=1 python3 solve.py REMOTE
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from pwn import *

from ctfharness.constants import FLAG_REGEX_DEFAULT

DEFAULT_HOST = "__HOST__"
DEFAULT_PORT = "__PORT__"
HOST = os.environ.get("HOST") or (DEFAULT_HOST if DEFAULT_HOST != "__HOST__" else "127.0.0.1")
PORT = int(os.environ.get("PORT") or (DEFAULT_PORT if str(DEFAULT_PORT).isdigit() else "0"))
SSL = bool(int(os.environ.get("SSL", "0")))
BINARY = os.environ.get("BINARY", "./artifacts/binary")
LIBC = os.environ.get("LIBC", "./artifacts/libc.so.6")

context.log_level = os.environ.get("LOG_LEVEL", "info")
FLAG_RE = re.compile(FLAG_REGEX_DEFAULT.encode())

try:
    context.binary = elf = ELF(BINARY, checksec=False)
except Exception:
    elf = None
try:
    libc = ELF(LIBC, checksec=False)
except Exception:
    libc = None

GDB_SCRIPT = """
set follow-fork-mode child
set pagination off
b *main
continue
"""
TRANSCRIPT: list[bytes] = []


def start() -> tube:
    if "REMOTE" in sys.argv:
        if not PORT:
            log.error("PORT is empty — set HOST/PORT env vars or edit template")
        return remote(HOST, PORT, ssl=SSL)
    if "GDB" in sys.argv:
        return gdb.debug([BINARY], gdbscript=GDB_SCRIPT, aslr=False)
    return process([BINARY])


def recv_available(io: tube, timeout: float = 3.0) -> bytes:
    try:
        data = io.recvrepeat(timeout)
    except EOFError:
        data = b""
    TRANSCRIPT.append(data)
    return data


def exploit(io: tube) -> bytes | None:
    # Replace this probe with your real exploit chain.
    banner = recv_available(io, timeout=2.0)
    log.info(f"banner ({len(banner)} bytes): {banner[:120]!r}")
    try:
        io.sendline(b"AAAA")
    except Exception:
        pass
    response = recv_available(io, timeout=5.0)
    log.info(f"response ({len(response)} bytes): {response[:120]!r}")
    full = b"\n".join(TRANSCRIPT)
    hit = FLAG_RE.search(full)
    return hit.group(0) if hit else None


def save_transcript() -> None:
    out = Path("transcript_pwn.bin")
    out.write_bytes(b"\n---\n".join(TRANSCRIPT))
    log.info(f"transcript saved: {out} ({out.stat().st_size} bytes)")


def main() -> int:
    io = start()
    flag = None
    try:
        flag = exploit(io)
    finally:
        try:
            io.close()
        except Exception:
            pass
    save_transcript()
    if flag:
        print(f"FLAG={flag.decode(errors='replace')}")
        return 0
    print("[-] no flag found yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
