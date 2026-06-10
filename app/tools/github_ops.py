import json
import subprocess
from typing import Any, Dict, Optional

from app.agent_paths import resolve_agent_path
from app.mcp_server import mcp
from app.logging_audit import log_audit_event
from app.security import format_error_response, validate_relative_path


def _validate_repo(repo: str) -> None:
    parts = repo.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("repo must be in 'owner/name' format.")


def _run_gh(args: list[str], cwd: Optional[str] = None, timeout_seconds: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args],
        cwd=cwd,
        capture_output=True,
        timeout=timeout_seconds,
        text=True,
        check=True,
    )


@mcp.tool(
    name="github_clone_or_sync",
    description="Clone a GitHub repo into the host workspace or sync an existing checkout there."
)
def github_clone_or_sync(repo: str, dst_in_workspace: str, branch: str = "") -> Dict[str, Any]:
    try:
        _validate_repo(repo)
        validate_relative_path(dst_in_workspace)

        dst = resolve_agent_path(dst_in_workspace)
        dst.parent.mkdir(parents=True, exist_ok=True)

        if (dst / ".git").exists():
            _run_gh(["repo", "sync", repo], cwd=str(dst), timeout_seconds=120)
            if branch:
                subprocess.run(["git", "checkout", branch], cwd=str(dst), capture_output=True, text=True, check=True)
                subprocess.run(["git", "pull", "--ff-only", "origin", branch], cwd=str(dst), capture_output=True, text=True, check=True)
            action = "synced"
        else:
            clone_args = ["repo", "clone", repo, str(dst)]
            if branch:
                clone_args.extend(["--", "--branch", branch])
            _run_gh(clone_args, timeout_seconds=180)
            action = "cloned"

        log_audit_event("GITHUB_CLONE_OR_SYNC", {"repo": repo, "dst": str(dst), "action": action, "branch": branch})
        return {"ok": True, "repo": repo, "dst": str(dst), "action": action, "branch": branch}
    except subprocess.CalledProcessError as e:
        return format_error_response(RuntimeError(e.stderr or e.stdout or str(e)))
    except Exception as e:
        return format_error_response(e)


@mcp.tool(
    name="github_list_prs",
    description="List pull requests for a GitHub repo using the GitHub CLI instead of a generic shell command."
)
def github_list_prs(repo: str, state: str = "open", limit: int = 20) -> Dict[str, Any]:
    try:
        _validate_repo(repo)
        limit = max(1, min(int(limit), 100))
        res = _run_gh(
            [
                "pr", "list",
                "--repo", repo,
                "--state", state,
                "--limit", str(limit),
                "--json", "number,title,headRefName,baseRefName,state,url,author",
            ]
        )
        prs = json.loads(res.stdout or "[]")
        return {"ok": True, "repo": repo, "pull_requests": prs}
    except subprocess.CalledProcessError as e:
        return format_error_response(RuntimeError(e.stderr or e.stdout or str(e)))
    except Exception as e:
        return format_error_response(e)


@mcp.tool(
    name="github_open_pr",
    description="Open a pull request on GitHub with explicit structured arguments instead of a shell command."
)
def github_open_pr(repo: str, head: str, base: str, title: str, body: str = "") -> Dict[str, Any]:
    try:
        _validate_repo(repo)
        args = ["pr", "create", "--repo", repo, "--head", head, "--base", base, "--title", title]
        if body:
            args.extend(["--body", body])
        else:
            args.append("--fill")
        res = _run_gh(args, timeout_seconds=120)
        url = res.stdout.strip()
        log_audit_event("GITHUB_OPEN_PR", {"repo": repo, "head": head, "base": base, "title": title})
        return {"ok": True, "repo": repo, "head": head, "base": base, "title": title, "url": url}
    except subprocess.CalledProcessError as e:
        return format_error_response(RuntimeError(e.stderr or e.stdout or str(e)))
    except Exception as e:
        return format_error_response(e)


@mcp.tool(
    name="github_get_run_logs",
    description="Fetch GitHub Actions run logs through the GitHub CLI, avoiding generic gh api shell usage."
)
def github_get_run_logs(repo: str, run_id: int, attempt: int = 0) -> Dict[str, Any]:
    try:
        _validate_repo(repo)
        args = ["run", "view", str(run_id), "--repo", repo, "--log"]
        if attempt > 0:
            args.extend(["--attempt", str(attempt)])
        res = _run_gh(args, timeout_seconds=180)
        return {"ok": True, "repo": repo, "run_id": run_id, "attempt": attempt, "log": res.stdout}
    except subprocess.CalledProcessError as e:
        return format_error_response(RuntimeError(e.stderr or e.stdout or str(e)))
    except Exception as e:
        return format_error_response(e)
