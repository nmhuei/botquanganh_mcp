#!/usr/bin/env python3
"""Verifier placeholder.

This script is intentionally conservative: it does NOT prove a flag is correct.
Use it only as a template. For real `verified` evidence, replace this script with
one of:

- a CTFd API submitter using a token from environment variables,
- an organizer-provided local checker,
- a challenge-specific verifier that exits 0 only on accepted flags.

By default this script exits 2 to avoid accidentally marking arbitrary candidates
as verified.
"""
from __future__ import annotations

import os
import re
import sys

flag = os.environ.get("FLAG") or (sys.argv[1] if len(sys.argv) > 1 else "")
if not flag:
    print("missing flag", file=sys.stderr)
    sys.exit(2)
if re.search(r"(?i)(fake|dummy|test|local|example|placeholder)", flag):
    print("rejected: decoy-looking flag", file=sys.stderr)
    sys.exit(1)
print("placeholder verifier: replace with real CTFd/checker before enabling proof.command", file=sys.stderr)
sys.exit(2)
