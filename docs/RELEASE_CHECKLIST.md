# Release Readiness Checklist

## Source and review

- [ ] Working branch and baseline commit are recorded.
- [ ] `git status --short` contains only intended changes.
- [ ] `git diff --check` passes.
- [ ] The full diff has been reviewed for scope, compatibility, and credential exposure.
- [ ] No unrelated generated/manual test directories are included.

## Automated quality

```bash
./scripts/quality_gate.sh --full
```

- [ ] Full pytest suite passes.
- [ ] compileall and Bash syntax pass.
- [ ] Project dependency closure passes.
- [ ] Config validation passes.
- [ ] Local and public doctor checks pass or warnings are explicitly accepted.
- [ ] Isolated lifecycle regression passes.

## Security checks

```bash
uvx bandit -q -r app
uvx pip-audit -r requirements.txt
uvx detect-secrets scan --all-files \
  --exclude-files '(^|/)(\.env$|\.venv/|logs/|artifacts/|manual_test_workspace_|\.pytest_cache/)'
```

- [ ] SAST findings are triaged; no unresolved High/Critical finding remains.
- [ ] Dependency advisories are triaged against installed and manifest versions.
- [ ] Secret scan reports no confirmed secret.
- [ ] `.env` is not tracked and uses mode `600`.
- [ ] Production authentication is enabled with a newly rotated token.
- [ ] `HOST_WORKSPACE_DIR` and command policy are production-appropriate.
- [ ] Command/rate capacity limits are sized for the host.

## Runtime and recovery

- [ ] `bqa status` reports owned supervisor/server/tunnel processes.
- [ ] `bqa server restart` preserves tunnel PID and URL.
- [ ] Local and public REST health pass.
- [ ] Local and public MCP initialize pass.
- [ ] Redacted diagnostics can be collected.
- [ ] Recovery and rollback commands from `OPERATIONS_RUNBOOK.md` are verified.

## Packaging and automation

- [ ] `bqa` works from a directory outside the repository.
- [ ] `./scripts/manual_test_installer.sh` passes local, piped, remote-clone, update, dirty-tree, origin-mismatch, and invalid-branch cases.
- [ ] Global install/uninstall tests pass.
- [ ] GitHub quality workflow is reviewed.
- [ ] GitHub Actions are pinned to immutable commit SHAs.
- [ ] Workflow permissions use least privilege.
- [ ] Dependabot configuration covers Python and GitHub Actions.

## Release decision

Release status must be one of:

- `READY`: all mandatory checks pass and production-only warnings are resolved.
- `READY_WITH_ACCEPTED_RISK`: warnings are documented with owner, scope, control, and review date.
- `NOT_READY`: a blocker, unresolved High/Critical finding, failed gate, or missing authorized runtime check remains.

The current development runtime with `REQUIRE_AUTH=false` cannot be classified as production `READY`.
