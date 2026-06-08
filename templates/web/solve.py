#!/usr/bin/env python3
"""CTF Harness — WEB solver template.
Challenge : __CHALLENGE__
Remote    : __HOST__:__PORT__

Usage:
  python3 solve.py --local http://127.0.0.1:1337
  python3 solve.py --remote https://target.ctf.example
  REMOTE_URL=https://target python3 solve.py REMOTE
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
import urllib3

from ctfharness.constants import FLAG_REGEX_DEFAULT

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_HOST = "__HOST__"
DEFAULT_PORT = "__PORT__"
FLAG_RE = re.compile(FLAG_REGEX_DEFAULT)
TRANSCRIPT: list[dict] = []

s = requests.Session()
s.verify = False
s.headers.update({"User-Agent": "ctf-harness-web/1.0"})


def record(method: str, url: str, status: int, body: str) -> None:
    TRANSCRIPT.append({"ts": time.time(), "method": method, "url": url, "status": status, "body_sample": body[:4000]})


def req(method: str, base: str, path: str = "/", **kwargs) -> requests.Response:
    url = urljoin(base.rstrip("/") + "/", path.lstrip("/"))
    r = s.request(method, url, timeout=15, **kwargs)
    print(f"[http] {method} {r.url} -> {r.status_code} ({len(r.text)} bytes)")
    record(method, str(r.url), r.status_code, r.text)
    return r


def extract_flag(text: str) -> str | None:
    hit = FLAG_RE.search(text)
    return hit.group(0) if hit else None


def exploit(base: str) -> str | None:
    # Replace recon paths with the confirmed exploit chain.
    for path in ["/", "/robots.txt", "/sitemap.xml", "/.git/HEAD", "/.env", "/flag", "/flag.txt", "/api/flag"]:
        try:
            r = req("GET", base, path)
        except requests.RequestException as exc:
            print(f"[!] {path}: {exc}")
            continue
        flag = extract_flag(r.text)
        if flag:
            return flag
    return None


def resolve_base() -> str:
    env = os.environ.get("REMOTE_URL") or os.environ.get("BASE_URL")
    if env:
        return env
    host = DEFAULT_HOST if DEFAULT_HOST != "__HOST__" else "127.0.0.1"
    port = DEFAULT_PORT if DEFAULT_PORT and DEFAULT_PORT != "__PORT__" else "80"
    scheme = "https" if port == "443" else "http"
    return f"{scheme}://{host}:{port}"


def save_transcript(flag: str | None) -> None:
    Path("transcript_web.json").write_text(json.dumps({"flag": flag, "events": TRANSCRIPT}, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[+] transcript saved: transcript_web.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", nargs="?", choices=["LOCAL", "REMOTE"])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--local")
    g.add_argument("--remote")
    ap.add_argument("--base")
    args = ap.parse_args()
    base = args.base or args.local or args.remote or resolve_base()
    print(f"[*] target: {base}")
    flag = exploit(base)
    save_transcript(flag)
    if flag:
        print(f"FLAG={flag}")
        return 0
    print("[-] no flag found yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
