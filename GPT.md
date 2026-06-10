# CTF Harness Operating Instructions

Use this document as the required operating guide before solving a CTF challenge
through this MCP server.

## Mission

Solve the challenge with evidence. Do not report a flag unless it is produced by
a working local or remote exploit path and matches the challenge format.

Default pipeline:

```text
TRIAGE -> RECON -> HYPOTHESIS -> EXPLOIT -> VERIFY -> REPORT
```

Never skip directly from recon to final answer. If a phase fails, record the
reason and pivot with a new hypothesis.

## Working Rules

- Work inside the challenge workspace, not random repo paths.
- Prefer local reproduction before remote exploitation.
- Keep solvers small until the primitive is proven.
- Record commands, outputs, and artifacts that justify the solve.
- Treat remote flag-like output as a candidate until verified.
- If blocked, name the exact missing fact or failed assumption.

## Coding Guardrails

- Think before coding: state the assumption and the cheapest command that can
  confirm or reject it.
- Prefer one clear `solve.py` over a large helper framework until the exploit
  is validated.
- Touch only files related to the current challenge or harness task.
- Do not hide failed attempts; keep useful failures as evidence for pivots.
- Every script should have a concrete success criterion and a timeout for
  network or brute-force loops.
- If the exploit needs a dependency, explain why the standard library or
  existing challenge tooling is not enough.

## Phase 1: Triage

Identify:

- category: `web`, `pwn`, `crypto`, `reverse`, `forensics`, `misc`, `osint`,
  `ai-ml`, or mixed
- provided files, URLs, ports, credentials, and challenge text
- local-vs-remote boundary
- expected flag format
- relevant skill file under `skills/ctf-<category>/SKILL.md`

Create or inspect:

```text
ctf.yaml
workspaces/<challenge>/
```

## Phase 2: Recon

Use the cheapest discriminators first.

Category starts:

```text
web       routes, source, headers, cookies, JS, auth, sinks
pwn       file, checksec, strings, run once, readelf, libc
crypto    parameters, oracle behavior, randomness, padding, key reuse
reverse   strings, symbols, imports, decompiler/disassembler, runtime checks
forensics file, binwalk, exiftool, strings, archive layers
misc      protocol/encoding/state machine split
osint     scope, entities, exact phrases, timestamps, images
ai-ml     model format, metadata, tensors, inference behavior
```

Save useful outputs under `workspaces/<challenge>/recon/` or harness artifacts.

## Phase 3: Hypothesis

Write a ranked list:

```text
H1: likely bug/primitive
Evidence:
Expected result:
Next command:
Fallback:
```

Do not retry the same failing command without changing an input or assumption.

## Phase 4: Exploit

Build the smallest working exploit:

```text
workspaces/<challenge>/exploit/solve.py
```

Rules:

- no broad framework unless the challenge requires it
- no unrelated refactors
- no destructive commands
- include timeouts for network loops
- add small sleeps for remote rate limits when needed
- keep failed attempts if they explain pivots

## Phase 5: Verify

A solve is verified only when at least one is true:

- local harness verifier accepts the result
- remote challenge accepts the flag
- deterministic exploit output directly reads/derives the flag from the intended
  target and evidence is captured

Record:

```text
command used
target used
stdout/stderr or transcript
flag candidate
verification result
```

## Phase 6: Report

Generate a concise writeup:

```text
workspaces/<challenge>/writeup.md
```

Include:

- summary
- target
- vulnerability/key insight
- exploit chain
- reproduction command
- verification evidence
- final solver path

## MCP Tool Order

Recommended first calls:

```text
ctf_harness_instructions
ctf_harness_capabilities
ctf_harness_check
run_safe_smoke_test
```

For lightweight solver execution:

```text
run_basic_python_solver
probe_target_from_runner
tcp_connect_ssl
```

For full harness flow:

```text
ctf_harness_init
ctf_harness_local
ctf_harness_solve
ctf_harness_verify
ctf_harness_report
ctf_harness_pack
```

Use advanced/agent tools only when the connector profile exposes them and the
task really needs local command/file control.

## Workspace Convention

```text
workspaces/<challenge>/
  ctf.yaml or copied config
  recon/
  exploit/
    solve.py
    attempts/
  artifacts/
  proof/
  writeup.md
```

## Final Answer Standard

Final answers must distinguish:

```text
verified flag
candidate flag
local-only proof
remote accepted proof
blocked / partial result
```

No working exploit means no claimed solve.
