"""Shared constants for CTF Harness.

Keep challenge-wide defaults here so CLI, templates, scripts and examples do not
silently drift apart.
"""
from __future__ import annotations

FLAG_REGEX_DEFAULT = (
    r"(?i)(?:FLAG|CTF|picoCTF|HTB|DUCTF|SEKAI|idekCTF|ictf|TBTL|KCSC|GPNCTF|THCON|1337UP|L3AK|n00bz)"
    r"\{[^}\r\n]{4,300}\}"
)

REJECT_DECOY_WORDS_DEFAULT = [
    "fake", "dummy", "test", "local", "example", "placeholder",
]

AUTHORIZED_REMOTE_DOMAINS_DEFAULT = ["localhost", "127.0.0.1"]

SUPPORTED_CATEGORIES = [
    "web", "pwn", "rev", "reverse", "crypto",
    "forensics", "misc", "osint", "ai-ml", "cloud-ci",
]

WORKSPACE_ROOT = "workspaces"
