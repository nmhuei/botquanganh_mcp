# ctf-writeup

## Description

Writeup skill — generate a reproducible CTF solution report after solving. Use this
only after local or remote verification exists. No verified exploit means no final
flag claim.

## Required Inputs

Collect these files before writing:

```text
workspaces/<challenge>/state.json
workspaces/<challenge>/notes/NOTES.md
workspaces/<challenge>/recon/*
workspaces/<challenge>/exploit/solve.py
workspaces/<challenge>/evidence/*
```

## Output Path

```text
workspaces/<challenge>/writeup.md
```

## Writeup Structure

```markdown
# <Challenge Name> — <Category>

## Summary
One paragraph: bug class, exploit primitive, and final result.

## Target
- Category:
- Files:
- Remote:
- Flag format:

## Recon
Commands and important outputs only.

## Vulnerability / Key Insight
Explain the exact primitive:
- input controlled by attacker
- trust boundary
- vulnerable code/path
- why protection/check fails

## Exploit Strategy
Step-by-step chain.

## Local Verification
Show command and output proving the exploit works locally.

## Remote Verification
Show command and output proving the remote flag was obtained.

## Flag Evidence
- Flag:
- Source transcript:
- SHA256:
- Why this is not a decoy:

## Final Solver
Link or include the minimal solve script.

## Reproduce
Commands from clean checkout/artifacts to flag.

## Failed Attempts
Short bullet list of dead ends and why they failed.
```

## Evidence Standard

The flag section must include at least one:

- remote transcript containing the flag
- accepted submission output
- deterministic local decrypt/check output
- server response hash + exact command
- source-code path proving flag read/generation

## Red Flags

Do not write as solved when:

- only a test/sample flag was found
- `/flag` was self-created locally
- exploit works only against modified source
- remote response does not contain/accept the flag
- the flag is guessed from format
- evidence file is missing

## Minimal Template

```markdown
# {{name}} — {{category}}

## Summary

Solved by ...

## Evidence

```text
{{final command}}
{{final output}}
```

SHA256:

```text
{{sha256}}
```

Flag:

```text
{{flag}}
```

## Reproduction

```bash
{{commands}}
```
```
