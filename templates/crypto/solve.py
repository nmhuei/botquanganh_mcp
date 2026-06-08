#!/usr/bin/env python3
"""CTF Harness — CRYPTO solver template.
Challenge : __CHALLENGE__
Remote    : __HOST__:__PORT__

Usage:
  python3 solve.py
  HOST=h PORT=p python3 solve.py REMOTE
"""
from __future__ import annotations

import base64
import json
import math
import os
import re
import sys
from pathlib import Path

from Crypto.Util.number import bytes_to_long, long_to_bytes

from ctfharness.constants import FLAG_REGEX_DEFAULT

FLAG_RE_B = re.compile(FLAG_REGEX_DEFAULT.encode())
FLAG_RE_S = re.compile(FLAG_REGEX_DEFAULT)
DEFAULT_HOST = "__HOST__"
DEFAULT_PORT = "__PORT__"
HOST = os.environ.get("HOST") or (DEFAULT_HOST if DEFAULT_HOST != "__HOST__" else "127.0.0.1")
PORT = int(os.environ.get("PORT") or (DEFAULT_PORT if str(DEFAULT_PORT).isdigit() else "0"))


def xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def xor_key(data: bytes, key: bytes) -> bytes:
    return bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))


def scan_bytes(data: bytes) -> str | None:
    hit = FLAG_RE_B.search(data)
    return hit.group(0).decode(errors="replace") if hit else None


def scan_str(data: str) -> str | None:
    hit = FLAG_RE_S.search(data)
    return hit.group(0) if hit else None


def iroot(n: int, k: int) -> tuple[int, bool]:
    if n < 0:
        raise ValueError("negative n")
    if n == 0:
        return 0, True
    x = 1 << ((n.bit_length() + k - 1) // k)
    while True:
        y = ((k - 1) * x + n // (x ** (k - 1))) // k
        if y >= x:
            while (x + 1) ** k <= n:
                x += 1
            while x ** k > n:
                x -= 1
            return x, x ** k == n
        x = y


def batch_gcd(ns: list[int]) -> list[tuple[int, int, int]]:
    out = []
    for i, n in enumerate(ns):
        for j, m in enumerate(ns[:i]):
            g = math.gcd(n, m)
            if 1 < g < n and 1 < g < m:
                out.append((i, j, g))
    return out


def get_oracle():
    from pwn import remote
    if not PORT:
        raise RuntimeError("PORT not set")
    return remote(HOST, PORT)


def load_json(name: str = "challenge.json") -> dict:
    for p in [Path("artifacts") / name, Path(name), Path("..") / name]:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError(name)


def scan_all_artifacts() -> str | None:
    for root, _, files in os.walk("."):
        if ".venv" in root or "__pycache__" in root:
            continue
        for name in files:
            p = Path(root) / name
            try:
                if p.stat().st_size > 10_000_000:
                    continue
                hit = scan_bytes(p.read_bytes())
                if hit:
                    print(f"[+] flag found in file: {p}")
                    return hit
            except Exception:
                pass
    return None


def solve() -> str | None:
    flag = scan_all_artifacts()
    if flag:
        return flag
    # TODO: implement actual crypto attack.
    return None


def main() -> int:
    flag = solve()
    if flag:
        print(f"FLAG={flag}")
        return 0
    print("[-] no flag found yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
