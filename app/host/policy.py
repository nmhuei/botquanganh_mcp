from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

import app.config
from app.host.paths import host_workspace_dir


# These rules are intentionally small and explicit.  They prevent obvious
# machine-destroying operations; they are not presented as a sandbox.
_FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "remove_root",
        re.compile(r"(^|[;&|(`\s])rm\s+[^\n;]*(?:-rf|-fr|--recursive)[^\n;]*\s/(?:\s|$|[;&|)`])", re.IGNORECASE),
        "Recursive deletion of the filesystem root is blocked.",
    ),
    (
        "remove_root_glob",
        re.compile(r"rm\s+[^\n;]*(?:-rf|-fr|--recursive)[^\n;]*\s/\*", re.IGNORECASE),
        "Recursive deletion of root contents is blocked.",
    ),
    (
        "filesystem_format",
        re.compile(r"(^|[;&|(`\s])mkfs(?:\.|\s)", re.IGNORECASE),
        "Filesystem formatting is blocked.",
    ),
    (
        "raw_disk_zeroing",
        re.compile(r"dd\s+[^\n;]*if=/dev/(?:zero|urandom)[^\n;]*of=/dev/", re.IGNORECASE),
        "Raw writes to block devices are blocked.",
    ),
    (
        "raw_block_device_redirect",
        re.compile(r">\s*/dev/(?:sd[a-z]|nvme\d+n\d+|vd[a-z])", re.IGNORECASE),
        "Direct redirection to a block device is blocked.",
    ),
    (
        "fork_bomb",
        re.compile(r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", re.IGNORECASE),
        "Process fork bombs are blocked.",
    ),
    (
        "shutdown_host",
        re.compile(r"(^|[;&|(`\s])(?:shutdown|reboot|poweroff|halt)(?:\s|$|[;&|)`])", re.IGNORECASE),
        "Power-management commands are blocked through MCP.",
    ),
    (
        "privilege_escalation",
        re.compile(r"(^|[;&|(`\s])(?:sudo|su|doas|pkexec)(?:\s|$|[;&|)`])", re.IGNORECASE),
        "Privilege escalation is blocked through MCP host tools.",
    ),
)

# Used only when HOST_COMMAND_POLICY=allowlist.  The default guarded policy
# permits installed commands after the forbidden rules above have passed.
_DEFAULT_ALLOWLIST = {
    "awk", "basename", "cat", "chmod", "cmp", "cp", "curl", "cut", "date",
    "diff", "dirname", "docker", "docker-compose", "du", "echo", "env", "file",
    "find", "git", "gh", "go", "grep", "head", "id", "java", "javac", "jq",
    "ls", "make", "mkdir", "mv", "nmap", "node", "npm", "od", "paste", "pnpm",
    "printf", "ps", "pwd", "python", "python3", "rg", "rm", "rustc", "cargo",
    "sed", "sha256sum", "sort", "stat", "tail", "tar", "tee", "test", "timeout",
    "touch", "tr", "tree", "uname", "uniq", "unzip", "uv", "wc", "wget", "which",
    "xargs", "xxd", "zip",
}

_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
_DYNAMIC_SHELL_RE = re.compile(r"(?<!\\)(?:\$\(|`|[<>]\()")


def _split_shell_chain(command: str) -> list[str]:
    """Split shell command chains without breaking separators inside quotes."""
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0

    while index < len(command):
        char = command[index]
        if escaped:
            current.append(char)
            escaped = False
            index += 1
            continue
        if char == "\\" and quote != "'":
            current.append(char)
            escaped = True
            index += 1
            continue
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            current.append(char)
            index += 1
            continue
        if char == "\n" or char == ";" or char == "|":
            if char == "|" and index + 1 < len(command) and command[index + 1] == "|":
                index += 1
            segment = "".join(current).strip()
            if segment:
                segments.append(segment)
            current = []
            index += 1
            continue
        if char == "&":
            segment = "".join(current).strip()
            if segment:
                segments.append(segment)
            current = []
            index += 2 if index + 1 < len(command) and command[index + 1] == "&" else 1
            continue
        current.append(char)
        index += 1

    segment = "".join(current).strip()
    if segment:
        segments.append(segment)
    return segments


def _command_names(command: str) -> list[str]:
    names: list[str] = []
    for segment in _split_shell_chain(command):
        segment = segment.strip()
        if not segment:
            continue
        try:
            words = shlex.split(segment, posix=True)
        except ValueError:
            # Let the shell report malformed quoting, but policy should not
            # silently treat it as safe in allowlist mode.
            names.append("<parse-error>")
            continue
        index = 0
        while index < len(words) and _ENV_ASSIGNMENT_RE.match(words[index]):
            index += 1
        if index >= len(words):
            continue
        first = Path(words[index]).name
        if first == "env":
            index += 1
            while index < len(words) and _ENV_ASSIGNMENT_RE.match(words[index]):
                index += 1
            if index < len(words):
                first = Path(words[index]).name
        names.append(first)
    return names


def _inspect_recursive_rm(command: str) -> dict[str, Any] | None:
    """Reject recursive removal of absolute paths outside the host workspace."""
    workspace = host_workspace_dir()
    for segment in _split_shell_chain(command):
        try:
            words = shlex.split(segment, posix=True)
        except ValueError:
            continue
        if not words:
            continue
        command_name = Path(words[0]).name
        if command_name != "rm":
            continue
        flags = [word for word in words[1:] if word.startswith("-")]
        recursive = any("r" in flag.lstrip("-") or flag == "--recursive" for flag in flags)
        if not recursive:
            continue
        for word in words[1:]:
            if word.startswith("-"):
                continue
            candidate = Path(word).expanduser()
            if not candidate.is_absolute():
                continue
            resolved = candidate.resolve(strict=False)
            try:
                resolved.relative_to(workspace)
            except ValueError:
                return {
                    "allowed": False,
                    "severity": "forbidden",
                    "rule": "recursive_remove_outside_workspace",
                    "matched_fragment": word,
                    "message": "Recursive removal outside HOST_WORKSPACE_DIR is blocked.",
                }
    return None


def inspect_host_command(command: str) -> dict[str, Any]:
    """Inspect a host command according to the server-side policy.

    ``guarded`` (default) allows normal host tooling after explicit destructive
    operations are rejected. ``allowlist`` additionally requires every command
    in a shell chain to be listed in the built-in or configured allowlist.
    There is deliberately no caller-supplied approval bypass.
    """
    if not isinstance(command, str) or not command.strip():
        return {
            "allowed": False,
            "severity": "invalid",
            "rule": "empty_command",
            "message": "Command must not be empty.",
        }
    if "\x00" in command:
        return {
            "allowed": False,
            "severity": "invalid",
            "rule": "null_byte",
            "message": "Command contains a null byte.",
        }

    for rule, pattern, message in _FORBIDDEN_PATTERNS:
        match = pattern.search(command)
        if match:
            return {
                "allowed": False,
                "severity": "forbidden",
                "rule": rule,
                "matched_fragment": match.group(0).strip()[:200],
                "message": message,
            }

    recursive_rm = _inspect_recursive_rm(command)
    if recursive_rm:
        return recursive_rm

    policy = app.config.HOST_COMMAND_POLICY
    names = _command_names(command)
    if policy == "allowlist":
        dynamic = _DYNAMIC_SHELL_RE.search(command)
        if dynamic:
            return {
                "allowed": False,
                "severity": "policy",
                "rule": "dynamic_shell_not_allowlisted",
                "matched_fragment": dynamic.group(0),
                "command_names": names,
                "message": (
                    "Command substitution and process substitution are not allowed "
                    "when HOST_COMMAND_POLICY=allowlist."
                ),
            }
        allowed_commands = _DEFAULT_ALLOWLIST | set(app.config.HOST_ALLOWED_COMMANDS)
        denied = [name for name in names if name not in allowed_commands]
        if denied:
            return {
                "allowed": False,
                "severity": "policy",
                "rule": "command_not_allowlisted",
                "matched_fragment": denied[0],
                "command_names": names,
                "message": (
                    f"Command '{denied[0]}' is not in the host allowlist. "
                    "Add it to HOST_ALLOWED_COMMANDS or use HOST_COMMAND_POLICY=guarded."
                ),
            }

    return {
        "allowed": True,
        "severity": "none",
        "rule": None,
        "policy": policy,
        "command_names": names,
    }


def require_host_command_allowed(command: str) -> dict[str, Any]:
    result = inspect_host_command(command)
    if not result["allowed"]:
        raise PermissionError(
            f"Host command blocked: rule={result.get('rule')}; "
            f"message={result.get('message')}"
        )
    return result
