---
name: solve-challenge
description: Orchestrator entry point for any CTF challenge. Detects category, loads the correct category skill, and executes the local-first evidence pipeline.
---

# solve-challenge — Orchestrator

## Trigger

Use this skill for every new challenge. It routes to the right category skill and manages the overall pipeline.

## Category Detection

| Signals | Category |
|---------|----------|
| binary, ELF, buffer overflow, heap, stack, shellcode, ROP, libc | pwn |
| RSA, AES, cipher, encrypt, decrypt, modulus, hash, XOR, LFSR, nonce | crypto |
| URL, HTTP, SQL, XSS, cookie, JWT, SSRF, upload, login, API | web |
| anti-debug, obfuscation, keygen, crackme, decompile | reverse |
| pcap, memory dump, disk image, steganography, EXIF, metadata | forensics |
| encoding, jail, pyjail, bash jail, protocol | misc |
| username, geolocation, WHOIS, social media | osint |
| model, neural network, adversarial, LLM, prompt injection | ai-ml |
| GitHub Actions, CI/CD, cloud, IAM, S3, cache poisoning | cloud-ci |

Ambiguous challenges may load two skills; start with the one that has the most concrete artifacts.

## Workspace Setup

```bash
ctfh init --name <slug> --category <cat> [--host host] [--port port]
ctfh check
# or
./scripts/new-challenge.sh <name> <category> [host] [port]
```

Workspace:

```text
workspaces/<name>/
├── artifacts/
├── exploit/solve.py
├── exploit/attempts/
├── recon/
├── notes/NOTES.md
├── evidence/
├── proofs/
├── logs/
├── transcripts/
├── payloads/
├── tmp/
└── state.json
```

## Pipeline

Follow: `TRIAGE → RECON → HYPOTHESIS → EXPLOIT → VERIFY → REPORT`.

Commands:

```bash
ctfh local --solve
ctfh verify --mode local
ctfh remote
ctfh verify --mode remote
ctfh report
ctfh pack
```

## Evidence Rules

| Status | Meaning |
|--------|---------|
| candidate-local | Flag-like token found locally; primitive proof only |
| candidate | Flag-like token found from remote artifacts/transcript |
| verified | Explicit verifier command accepted it |
| suspect-decoy | Reject-word hit such as fake/test/local |

Remote `candidate` is not automatically `verified`. Set `proof.command` to a real checker/CTFd submitter for final proof.

## Failure Protocol

After three meaningful pivots, write the blocker to `state.json`, preserve failed attempts in `exploit/attempts/`, and do not fabricate a flag.
