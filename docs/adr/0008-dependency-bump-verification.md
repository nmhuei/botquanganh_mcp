---
adr: 0008
title: Dependency-bump PRs merge only after a local pytest rehearsal
status: Accepted
date: 2026-08-26
---

## Context

Dependabot opened two version-bump PRs (#4: `fastmcp==3.4.0` → `3.4.7`, #5:
`python-dotenv` → `1.2.3`) while main carried a heavy volume of unpushed
churn. Merging such bumps blind risks runtime regressions on the host MCP
server, but blocking every automated merge on a manual testing round defeats
the purpose of the automation and does not scale to future bumps. Meanwhile
the repo ships its own pin-guard suite
(`tests/test_dependency_check.py`), which deliberately fails whenever the
installed environment diverges from the declared pins — so a naive
"everything must be green" gate is impossible to satisfy mid-bump and an
explicit acceptance procedure is required instead.

## Decision

1. Local rehearsal before merge: every dependency-bump PR is verified in a
   throwaway uv virtualenv created outside the repo (per the large-artifacts
   Downloads policy) before its changes are merged. The rehearsal installs
   the bumped pin plus the repo itself with `--no-deps`, so exactly the PR's
   proposed dependency set is exercised.
2. Tolerated failure set: the rehearsal runs the full pytest suite, and the
   ONLY tolerated failures are the two pin-guard assertions in
   `tests/test_dependency_check.py` (installed vs declared pins disagree,
   since the PR's manifest changes are not yet applied locally). Those flip
   green once the PR lands. Any other failure blocks the merge.
3. Differential oracle for parser-behavioral deps: a dependency whose
   behavior the runtime depends on at parse time (python-dotenv backs the
   dependency-free `.env` loader `app.config._load_env_file`) additionally
   requires the differential oracle suite
   (`tests/test_config_env_parity.py`) to be green against the new version,
   proving parsed-config parity across the bump.
4. Lockstep manifests: both manifests must move together — verified by
   inspecting the PR diff shape (pin change in `pyproject.toml` paired with
   the corresponding lockfile update); a PR touching only one is rejected as
   incomplete.
5. Sequential merging: when several open PRs touch the same manifests, they
   merge strictly one after another (each re-based or superseded by
   Dependabot), never interleaved, so each rehearsal result stays valid for
   the commit it approved.

## Consequences

- After a passing rehearsal, merging becomes a one-click action; no manual
  smoke-testing round stands between a green rehearsal and the merge button.
- Rehearsal artifacts (venvs, logs) live outside the repository under
  `~/Downloads/` per project policy and can be discarded freely; nothing in
  the repo depends on them.
- The pin-guard tests become the single source of truth for
  installed-vs-declared consistency: a clean checkout after any accepted
  bump must show them green, and their red state during a rehearsal is the
  documented, expected signal rather than a defect.
