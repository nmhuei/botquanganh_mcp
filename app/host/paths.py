from pathlib import Path
from typing import Optional

import app.config


def host_workspace_dir() -> Path:
    """Return the configured host workspace as an absolute path."""
    return app.config.HOST_WORKSPACE_DIR.resolve()


def resolve_host_path(
    user_path: Optional[str],
    *,
    must_exist: bool = False,
    expect_directory: Optional[bool] = None,
) -> Path:
    """Resolve a user path under the configured host workspace policy.

    Relative paths are resolved from ``HOST_WORKSPACE_DIR``.  Absolute paths
    are accepted only when ``HOST_RESTRICT_TO_WORKSPACE`` is disabled or the
    resolved path remains inside the workspace.
    """
    base_dir = host_workspace_dir()
    raw = Path(user_path or ".").expanduser()
    resolved = raw if raw.is_absolute() else base_dir / raw
    resolved = resolved.resolve()

    if app.config.HOST_RESTRICT_TO_WORKSPACE:
        try:
            resolved.relative_to(base_dir)
        except ValueError as exc:
            raise PermissionError(
                f"Access denied. Path '{user_path}' is outside HOST_WORKSPACE_DIR "
                f"('{base_dir}')."
            ) from exc

    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"Path not found: {resolved}")
    if expect_directory is True and resolved.exists() and not resolved.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {resolved}")
    if expect_directory is False and resolved.exists() and not resolved.is_file():
        raise ValueError(f"Path is not a regular file: {resolved}")
    return resolved


def display_host_path(path: Path) -> str:
    """Prefer a workspace-relative path in MCP responses."""
    base_dir = host_workspace_dir()
    try:
        return str(path.resolve().relative_to(base_dir)) or "."
    except ValueError:
        return str(path.resolve())
