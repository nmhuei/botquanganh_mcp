from __future__ import annotations

import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any, Mapping

SECRET_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "PASSWD", "API_KEY", "PRIVATE_KEY")
DEFAULTS: dict[str, str] = {
    "MCP_BIND_HOST": "127.0.0.1",
    "MCP_CONNECT_HOST": "127.0.0.1",
    "MCP_PORT": "18427",
    "MCP_PATH": "/mcp",
    "MCP_JSON_RESPONSE": "true",
    "MCP_STATELESS_HTTP": "true",
    "REQUIRE_AUTH": "false",
    "GATEWAY_TOKEN": str(),
    "TRUST_PROXY_HEADERS": "false",
    "ALLOWED_ORIGINS": "",
    "HOST_WORKSPACE_DIR": str(Path.home()),
    "HOST_RESTRICT_TO_WORKSPACE": "true",
    "HOST_DEFAULT_DIR": str(Path.home()),
    "HOST_READ_SCOPE": "",
    "HOST_WRITE_SCOPE": "",
    "HOST_READ_DENY_GLOBS": "",
    "HOST_COMMAND_POLICY": "guarded",
    "HOST_ALLOWED_COMMANDS": "all",
    "HOST_INHERIT_ENV": "true",
    "HOST_ENV_ALLOWLIST": "",
    "HOST_KNOWLEDGE_DIR": "./knowledge",
    "HOST_TOOL_CACHE_SECONDS": "300",
    "MAX_SINGLE_FILE_BYTES": "3000000",
    "MAX_OUTPUT_BYTES": "500000",
    "DEFAULT_TIMEOUT_SECONDS": "0",
    "MAX_TIMEOUT_SECONDS": "0",

    "MAX_CONCURRENT_COMMANDS": "100",
    "COMMAND_QUEUE_TIMEOUT_SECONDS": "2",
    "SEARCH_TEXT_DEADLINE_SECONDS": "15",
    "LOG_FILE": "./logs/gateway.log",
    "AUDIT_LOG_MAX_BYTES": "10000000",
    "AUDIT_LOG_BACKUP_COUNT": "5",
    "AUDIT_MAX_FIELD_CHARS": "4000",
    "ATTRIBUTION_MODE": "enforce",
    "HOST_CHAT_WORKSPACES": "true",
    "HOST_CHAT_ROOT": str(Path.home() / "Downloads" / "bqa-workspaces"),
    "HOST_CHAT_IDLE_ARCHIVE_HOURS": "72",
    "HOST_CHAT_RETENTION_DAYS": "30",
    "HOST_CHAT_MAX_WORKSPACES": "128",
    "HOST_CHAT_QUOTA_MB": "2048",
    "HOST_CHAT_ISOLATE": "false",
    "HOST_CHAT_RESUME_HINT_MINUTES": "30",
    "HOST_CHAT_ROOT_MAX_GB": "24",
    "HOST_CHAT_JOURNAL_MAX_BYTES": "8388608",
    "HOST_CHAT_SWEEP_INTERVAL_MINUTES": "60",
    "HOST_CHAT_SWEEP_APPLY": "false",
}

_BOOLEAN_KEYS = (
    "MCP_JSON_RESPONSE",
    "MCP_STATELESS_HTTP",
    "REQUIRE_AUTH",
    "TRUST_PROXY_HEADERS",
    "HOST_RESTRICT_TO_WORKSPACE",
    "HOST_INHERIT_ENV",
    "HOST_CHAT_WORKSPACES",
    "HOST_CHAT_ISOLATE",
    "HOST_CHAT_SWEEP_APPLY",
)
_INTEGER_LIMITS: dict[str, tuple[int, int | None]] = {
    "MCP_PORT": (1, 65535),
    "HOST_TOOL_CACHE_SECONDS": (0, None),
    "MAX_SINGLE_FILE_BYTES": (1, None),
    "MAX_OUTPUT_BYTES": (1, None),
    "DEFAULT_TIMEOUT_SECONDS": (0, None),
    "MAX_TIMEOUT_SECONDS": (0, None),
    "MAX_CONCURRENT_COMMANDS": (1, 1024),

    "AUDIT_LOG_MAX_BYTES": (1024, None),
    "AUDIT_LOG_BACKUP_COUNT": (1, 1000),
    "AUDIT_MAX_FIELD_CHARS": (256, None),
    "HOST_CHAT_IDLE_ARCHIVE_HOURS": (0, None),
    "HOST_CHAT_RETENTION_DAYS": (0, None),
    "HOST_CHAT_MAX_WORKSPACES": (1, None),
    "HOST_CHAT_QUOTA_MB": (0, None),
    "HOST_CHAT_RESUME_HINT_MINUTES": (0, None),
    "HOST_CHAT_JOURNAL_MAX_BYTES": (1024, None),
    "HOST_CHAT_SWEEP_INTERVAL_MINUTES": (1, None),
}
_FLOAT_LIMITS: dict[str, tuple[float, float | None]] = {
    "COMMAND_QUEUE_TIMEOUT_SECONDS": (0.0, None),
    "SEARCH_TEXT_DEADLINE_SECONDS": (0.0, None),
    "HOST_CHAT_ROOT_MAX_GB": (0.0, None),
}
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def is_secret_key(key: str) -> bool:
    upper = key.upper()
    return any(marker in upper for marker in SECRET_MARKERS)


def redact_value(key: str, value: Any) -> Any:
    if is_secret_key(key) and value not in {None, ""}:
        return "********"
    return value


def load_env(repo_root: Path) -> dict[str, str]:
    values: dict[str, str] = dict(DEFAULTS)
    env_file = repo_root / ".env"
    if env_file.exists():
        from dotenv import dotenv_values  # local: keep python-dotenv off the CLI import path

        for key, value in dotenv_values(env_file).items():
            if value is not None:
                values[str(key)] = str(value)
    for key in set(values) | {"BQA_TOKEN", "BQA_BASE_URL"}:
        if key in os.environ:
            values[key] = os.environ[key]
    return values


def bool_value(values: Mapping[str, str], key: str, default: bool = False) -> bool:
    raw = values.get(key)
    if raw is None:
        return default
    return str(raw).strip().lower() in _TRUE_VALUES


def resolve_config_path(repo_root: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve(strict=False)


def _dotenv_quote(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("Configuration values must not contain a line break.")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _persist_env_updates(repo_root: Path, updates: Mapping[str, str]) -> dict[str, str]:
    """Atomically persist selected non-secret settings while preserving .env mode."""
    env_path = repo_root / ".env"
    try:
        existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        source_mode = stat.S_IMODE(env_path.stat().st_mode) if env_path.exists() else 0o600
    except OSError as exc:
        raise ValueError(f"Unable to read configuration file: {exc}") from exc

    key_pattern = "|".join(re.escape(key) for key in updates)
    pattern = re.compile(rf"^(?P<prefix>\s*)(?P<key>{key_pattern})\s*=.*$")
    found: set[str] = set()
    rendered: list[str] = []
    for line in existing.splitlines():
        match = pattern.match(line)
        if match:
            key = match.group("key")
            rendered.append(f"{match.group('prefix')}{key}={_dotenv_quote(updates[key])}")
            found.add(key)
        else:
            rendered.append(line)
    for key in updates:
        if key not in found:
            rendered.append(f"{key}={_dotenv_quote(updates[key])}")
    content = "\n".join(rendered).rstrip("\n") + "\n"

    try:
        descriptor, temporary = tempfile.mkstemp(prefix=".env.", dir=repo_root, text=True)
        temporary_path = Path(temporary)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_path, source_mode)
            os.replace(temporary_path, env_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise ValueError(f"Unable to save configuration file: {exc}") from exc

    return {key: str(value) for key, value in updates.items()}


def set_workspace_config(repo_root: Path, raw_workspace: str) -> dict[str, str]:
    """Persist a selected existing directory as the restricted host workspace.

    The desktop UI intentionally updates both workspace and default directory so
    the server's directory policy remains internally consistent after restart.
    Explicit environment variables take priority over ``.env`` at runtime, so
    refuse a misleading update when an operator exported either setting.
    """
    if any(key in os.environ for key in ("HOST_WORKSPACE_DIR", "HOST_DEFAULT_DIR")):
        raise ValueError(
            "HOST_WORKSPACE_DIR or HOST_DEFAULT_DIR is set in the current environment; "
            "unset it before changing the workspace through the UI."
        )

    if not isinstance(raw_workspace, str) or not raw_workspace.strip():
        raise ValueError("Selected workspace must be an existing directory.")
    selected = Path(raw_workspace).expanduser().resolve(strict=False)
    if not selected.is_dir():
        raise ValueError("Selected workspace must be an existing directory.")

    return _persist_env_updates(
        repo_root,
        {
            "HOST_WORKSPACE_DIR": str(selected),
            "HOST_DEFAULT_DIR": str(selected),
        },
    )


def safe_config(values: Mapping[str, str]) -> dict[str, str]:
    return {key: str(redact_value(key, value)) for key, value in sorted(values.items())}


def _parse_integer(value: str, minimum: int, maximum: int | None) -> tuple[bool, str]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return False, str(value)
    valid = parsed >= minimum and (maximum is None or parsed <= maximum)
    return valid, str(parsed)


def _parse_float(value: str, minimum: float, maximum: float | None) -> tuple[bool, str]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return False, str(value)
    valid = parsed >= minimum and (maximum is None or parsed <= maximum)
    return valid, str(parsed)


def validate_config(
    repo_root: Path,
    values: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    values = dict(values or load_env(repo_root))
    checks: list[dict[str, Any]] = []

    def add(name: str, status: str, message: str) -> None:
        checks.append({"name": name, "status": status, "message": message})

    env_path = repo_root / ".env"
    add("env_file", "pass" if env_path.is_file() else "fail", str(env_path))
    if env_path.is_file():
        mode = stat.S_IMODE(env_path.stat().st_mode)
        has_secret = any(
            is_secret_key(key) and str(value).strip()
            for key, value in values.items()
        )
        secure_mode = not has_secret or mode & 0o077 == 0
        add(
            "env_permissions",
            "pass" if secure_mode else "fail",
            f"mode={mode:03o}; expected no group/world access when secrets are present",
        )

    for key in _BOOLEAN_KEYS:
        raw = str(values.get(key, DEFAULTS[key])).strip().lower()
        add(
            f"config_{key.lower()}",
            "pass" if raw in _TRUE_VALUES | _FALSE_VALUES else "fail",
            raw,
        )

    for key, (minimum, maximum) in _INTEGER_LIMITS.items():
        valid, rendered = _parse_integer(values.get(key, DEFAULTS[key]), minimum, maximum)
        add(f"config_{key.lower()}", "pass" if valid else "fail", rendered)

    for key, (minimum, maximum) in _FLOAT_LIMITS.items():
        valid, rendered = _parse_float(values.get(key, DEFAULTS[key]), minimum, maximum)
        add(f"config_{key.lower()}", "pass" if valid else "fail", rendered)

    mcp_path = str(values.get("MCP_PATH", "/mcp")).strip()
    add(
        "mcp_path",
        "pass" if mcp_path.startswith("/") and " " not in mcp_path else "fail",
        mcp_path,
    )

    workspace = resolve_config_path(
        repo_root,
        values.get("HOST_WORKSPACE_DIR", str(Path.home())),
    )
    add("workspace", "pass" if workspace.is_dir() else "fail", str(workspace))

    knowledge = resolve_config_path(
        repo_root,
        values.get("HOST_KNOWLEDGE_DIR", "./knowledge"),
    )
    add("knowledge_dir", "pass" if knowledge.is_dir() else "fail", str(knowledge))
    catalog = knowledge / "TOOL_CATALOG.json"
    add("tool_catalog", "pass" if catalog.is_file() else "warn", str(catalog))

    policy = values.get("HOST_COMMAND_POLICY", "guarded").strip().lower()
    add(
        "command_policy",
        "pass" if policy in {"guarded", "allowlist"} else "fail",
        policy,
    )

    mode = values.get("ATTRIBUTION_MODE", "off").strip().lower()
    add(
        "attribution_mode",
        "pass" if mode in {"off", "tag", "strict", "enforce"} else "fail",
        mode,
    )

    auth_required = bool_value(values, "REQUIRE_AUTH", False)
    token_set = bool(values.get("GATEWAY_TOKEN", "").strip())
    if auth_required and not token_set:
        add("authentication", "fail", "REQUIRE_AUTH=true but GATEWAY_TOKEN is empty")
    elif auth_required:
        add("authentication", "pass", "enabled with token")
    else:
        add("authentication", "warn", "disabled by operator choice")

    cloudflared = shutil.which("cloudflared")
    add(
        "cloudflared",
        "pass" if cloudflared else "warn",
        cloudflared or "not found in PATH",
    )

    required_executables = {
        "fastmcp": repo_root / ".venv" / "bin" / "fastmcp",
        "cli_wrapper": repo_root / "bin" / "bqa",
        "process_helpers": repo_root / "scripts" / "process_helpers.sh",
    }
    for name, path in required_executables.items():
        add(
            name,
            "pass" if path.is_file() and os.access(path, os.X_OK) else "fail",
            str(path),
        )

    global_cli = shutil.which("bqa")
    expected_cli = (repo_root / "bin" / "bqa").resolve()
    global_ok = False
    if global_cli:
        try:
            global_ok = Path(global_cli).resolve() == expected_cli
        except OSError:
            global_ok = False
    add(
        "global_cli",
        "pass" if global_ok else "warn",
        global_cli or "not found in PATH",
    )

    log_file = resolve_config_path(repo_root, values.get("LOG_FILE", "./logs/gateway.log"))
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        writable = os.access(log_file.parent, os.W_OK)
    except OSError:
        writable = False
    add("audit_log_parent", "pass" if writable else "fail", str(log_file.parent))
    try:
        max_bytes = int(values.get("AUDIT_LOG_MAX_BYTES", DEFAULTS["AUDIT_LOG_MAX_BYTES"]))
        current_size = log_file.stat().st_size if log_file.exists() else 0
        add(
            "audit_log_size",
            "warn" if current_size > max_bytes else "pass",
            f"current={current_size}; rotate_at={max_bytes}",
        )
        free_bytes = shutil.disk_usage(log_file.parent).free
        add(
            "log_disk_free",
            "warn" if free_bytes < 100 * 1024 * 1024 else "pass",
            f"free_bytes={free_bytes}",
        )
    except (OSError, ValueError) as exc:
        add("audit_log_size", "fail", str(exc))

    try:
        from app.cli.lifecycle import process_matches
    except ImportError:  # pragma: no cover
        process_matches = None
    kind_map = {
        "launcher": "launcher",
        "watchdog": "supervisor",
        "server": "server",
        "tunnel": "tunnel",
    }
    for name, kind in kind_map.items():
        path = repo_root / "logs" / f"{name}.pid"
        if not path.exists():
            add(f"pid_{name}", "pass", "not present")
            continue
        try:
            pid = int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            add(f"pid_{name}", "warn", f"invalid PID file: {path}")
            continue
        owned = bool(process_matches and process_matches(pid, kind))
        add(
            f"pid_{name}",
            "pass" if owned else "warn",
            f"managed pid={pid}" if owned else f"stale or unrelated pid={pid}",
        )

    return checks
