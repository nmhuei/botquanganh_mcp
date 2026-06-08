# ctf-cloud-ci

## Description

Cloud/CI/CD skill — GitHub Actions, GitLab CI, package registries, cache poisoning,
artifact poisoning, release workflows, IaC misconfigurations, cloud metadata SSRF,
container registry issues, and deployment pipeline challenges.

Use this skill when challenge source contains `.github/workflows`, `.gitlab-ci.yml`,
Docker build pipelines, release jobs, cloud credentials, package publishing, or
metadata-service access.

## Prerequisites

```bash
apt-get install -y git gh jq curl docker.io
python3 -m pip install requests pyyaml --break-system-packages
```

## Recon Checklist

```bash
find . -maxdepth 5 -type f \( -path '*/.github/*' -o -name '.gitlab-ci.yml' -o -name 'Dockerfile' -o -name 'docker-compose.yml' -o -name 'package.json' -o -name 'pyproject.toml' -o -name 'Cargo.toml' \) -print
grep -RniE 'pull_request_target|workflow_run|cache|artifact|secret|FLAG|checkout|ref:|merge|release|upload-artifact|download-artifact|docker build|registry|token|GITHUB_TOKEN' .
```

## GitHub Actions Risk Map

| Signal | Risk |
|--------|------|
| `pull_request_target` + checkout PR ref | untrusted code with privileged token/secrets |
| cache restore/save across trust boundary | cache poisoning |
| artifact upload/download across workflows | artifact poisoning |
| release workflow consumes build output | release poisoning |
| `actions/checkout` with attacker-controlled ref | code injection |
| `${{ github.event.* }}` inside shell | command injection |
| unpinned actions | supply-chain pivot |
| `GITHUB_TOKEN` write permission | repo/content/PR mutation |
| secrets in build/test context | exfil path |

## Workflow Analysis Steps

1. List workflows and triggers.
2. Mark privileged contexts: secrets, write token, release deploy.
3. Mark attacker-controlled inputs: branch, PR title/body, artifact, cache key, file path.
4. Draw dataflow from untrusted input to privileged sink.
5. Reproduce in a throwaway/fork repo when possible.
6. Execute minimal benign proof before flag exfiltration.
7. Capture run ID, commit SHA, logs, artifact hash.

## Cache Poisoning Pattern

Check:

```yaml
actions/cache
path:
key:
restore-keys:
```

Exploit shape:

```text
untrusted job saves cache path → privileged job restores same cache → poisoned binary/script/dependency runs with secrets
```

Controls to inspect:

- branch included in key?
- event type included in key?
- hashFiles covers attacker-controlled lockfile?
- restore-keys too broad?
- path includes build outputs or dependencies that execute later?

## Artifact Poisoning Pattern

```text
untrusted workflow uploads artifact → privileged workflow downloads artifact by name → executes or packages it
```

Check:

- artifact name collision
- latest artifact chosen without run/commit validation
- missing checksum
- release job trusts artifact content
- workflow_run from PR branch

## GitHub CLI Useful Commands

```bash
gh repo view OWNER/REPO
gh workflow list
gh run list --limit 20
gh run view <run-id> --log
gh run download <run-id> -n <artifact-name> -D artifacts/downloaded
gh api repos/OWNER/REPO/actions/runs/<run-id>/artifacts | jq .
```

## Docker / Registry

```bash
docker build -t chall .
docker history image
grep -RniE 'ARG|ENV|SECRET|TOKEN|FLAG|COPY|ADD|RUN' Dockerfile .
```

Check:

- secret in build args/layers
- `.dockerignore` missing
- release image contains flag/source
- registry tag overwritten by attacker
- entrypoint trusts env/file from artifact

## Cloud Metadata SSRF

Targets:

```text
http://169.254.169.254/latest/meta-data/
http://metadata.google.internal/computeMetadata/v1/
http://169.254.169.254/metadata/instance?api-version=2021-02-01
```

Only test within authorized CTF infra.

## Verify

A cloud/CI flag is valid only when:

- It comes from the official workflow/job/artifact/release context, and
- Logs/artifacts show the exact chain, and
- You did not modify the challenge to self-create a flag.

Save:

```bash
gh run view <run-id> --log > evidence/run.log
sha256sum evidence/run.log artifacts/* > evidence/SHA256SUMS
```

## Pivot Rules

- CI exposes web app route → `ctf-web`
- Poisoned artifact is native binary exploit → `ctf-pwn`
- Secret is hidden in repo history → `ctf-osint` + `ctf-forensics`
- Docker runtime escape → `ctf-misc`
