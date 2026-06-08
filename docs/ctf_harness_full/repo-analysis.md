# Repo analysis → harness design

## KeygraphHQ/shannon

Useful ideas copied into the harness design:

- White-box + live exploitation flow.
- Multi-stage pipeline: pre-recon, recon, vulnerability class, exploitation, report.
- Proof-by-exploitation rather than speculative findings.
- Workspace state so interrupted work can resume and logs/deliverables stay organized.
- Explicit safety/scope boundary.

Harness translation:

- `ctf.yaml` declares target, local commands, remote target, solver commands, and flag policy.
- `ctfh local --solve` handles local build/start/smoke/solver.
- `ctfh remote` is gated by local proof.
- `ctfh report` creates proof-oriented Markdown.

## ljagiello/ctf-skills

Useful ideas copied into the harness design:

- Skill routing by CTF category.
- First-pass workflow and quick commands.
- Tool bootstrap scripts and per-category prerequisites.
- Pivot rules between web/pwn/rev/crypto/forensics/misc.

Harness translation:

- `templates/<category>/solve.py` provides category-specific solver skeletons.
- `scripts/install_ctf_tools_min.sh` gives a lightweight common tool installer.
- `skills/ctf-harness/SKILL.md` captures routing and workflow rules.

## openclaw/openclaw

Useful ideas copied into the harness design:

- Workspace as the agent home.
- Skills as markdown instruction directories with `SKILL.md`.
- Sandbox/container execution to limit blast radius.
- Multi-agent/session isolation as a useful mental model for separate challenge runs.
- Avoid committing secrets; logs and memory are private artifacts.

Harness translation:

- `workspaces/<challenge>/` is the per-challenge workspace.
- `skills/ctf-harness/SKILL.md` can be installed into an agent workspace.
- Dockerfile provides isolated CTF tool environment.
- `.gitignore` prevents credentials and artifacts from accidental commits.

## Resulting harness architecture

```text
ctf.yaml
  ├─ challenge metadata + flag regex
  ├─ local build/start/smoke/stop commands
  ├─ solver.local and solver.remote commands
  ├─ remote target/env
  └─ proof/verifier policy

ctfharness/
  ├─ cli.py           # workflow orchestration
  ├─ config.py        # config loading/normalization
  ├─ flag.py          # flag detection + evidence JSON
  ├─ logging_utils.py # command logs + SHA256
  └─ scope.py         # remote target allowlist check

workspaces/<challenge>/
  ├─ logs/
  ├─ proofs/
  ├─ payloads/
  ├─ transcripts/
  ├─ reports/
  └─ timeline.jsonl
```
