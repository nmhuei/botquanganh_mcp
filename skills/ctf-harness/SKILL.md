---
name: ctf-harness
description: Local-first CTF solving harness. Use when solving CTF challenges from source archives, Docker services, binaries, web apps, nc/ncat services, GitHub Actions challenge repos, forensics artifacts, reverse engineering puzzles, or misc automation tasks. It enforces local reproduction before remote exploitation, logs every command, verifies flag candidates, and produces a final evidence report.
license: MIT
compatibility: Requires bash, Python 3.10+, PyYAML, and optional Docker/pwntools/requests depending on challenge category.
allowed-tools: Bash Read Write Edit Glob Grep WebFetch WebSearch
metadata:
  user-invocable: "true"
---

# CTF Harness Skill

## Operating pattern

1. Create or reuse `ctf.yaml`.
2. Identify category: web, pwn, rev, crypto, forensics, misc, osint.
3. Build or emulate the local challenge exactly from provided artifacts.
4. Prove the primitive locally: leak, bypass, crash control, arbitrary read/write, source disclosure, token forgery, RCE, or solver output.
5. Run the remote solver only after local proof unless the operator explicitly overrides.
6. Treat local sample flags as non-final.
7. Verify remote flag candidates through transcript evidence and optional platform/verifier command.
8. Produce a report containing flag, proof, commands, logs, and SHA256 hashes.

## Standard commands

```bash
ctfh check
ctfh local --solve
ctfh verify --mode local
ctfh remote
ctfh verify --mode remote
ctfh report
ctfh pack
```

## Evidence rules

- A flag from local-only output is a primitive proof, not a final flag.
- A flag containing fake/test/local/dummy/example/placeholder is suspect.
- A flag from an official remote transcript plus SHA256 log is acceptable CTF evidence.
- A platform submission or challenge-provided verifier returning success upgrades evidence to strongest proof.

## Category routing

- Web: map routes, capture requests, inspect JS/source, test auth, parser mismatch, upload, SSRF, SQLi, SSTI, XSS/admin bot.
- Pwn: checksec, file, libc, protections, crash offset, leak, exploit chain, local pwntools, then remote pwntools/ncat.
- Reverse: strings, file, ltrace/strace, disassembly, Frida hook comparisons, symbolic execution, emulate if needed.
- Crypto: identify primitive, collect known plaintext, search for nonce reuse, weak PRNG, oracle, lattice, padding, MAC length-extension.
- Forensics: preserve original, hash input, extract layers, inspect metadata, carve files, analyze PCAP/memory/disk, then script recovery.
- Misc: identify environment/protocol/state machine, automate manual steps, write reproducible solver.

## Final response checklist

- Give the flag only when evidence is strong.
- Include why the flag is real.
- Include local proof summary.
- Include remote command/log path and transcript hash.
- Include concise log of actions performed.
