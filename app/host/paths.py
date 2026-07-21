from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import app.config


def host_workspace_dir() -> Path:
    """Return the configured host workspace as an absolute path."""
    return app.config.HOST_WORKSPACE_DIR.resolve()


def _lexical_absolute_path(user_path: Optional[str]) -> Path:
    base_dir = host_workspace_dir()
    raw = Path(user_path or ".").expanduser()
    candidate = raw if raw.is_absolute() else base_dir / raw
    # abspath removes `.` and `..` without following symlinks.
    return Path(os.path.abspath(candidate))


def _assert_workspace_boundary(path: Path, user_path: Optional[str]) -> None:
    if not app.config.HOST_RESTRICT_TO_WORKSPACE:
        return
    base_dir = host_workspace_dir()
    try:
        path.relative_to(base_dir)
    except ValueError as exc:
        raise PermissionError(
            f"Access denied. Path '{user_path}' is outside HOST_WORKSPACE_DIR "
            f"('{base_dir}')."
        ) from exc


def _assert_no_symlink_components(path: Path) -> None:
    """Reject existing symlink components before a filesystem operation.

    Final file operations also use ``O_NOFOLLOW`` where available. This
    component check prevents normal symlink traversal and the no-follow open
    protects the final component from being swapped between validation/open.
    """
    if not app.config.HOST_RESTRICT_TO_WORKSPACE:
        start = Path(path.anchor)
        parts = path.parts[1:]
    else:
        start = host_workspace_dir()
        try:
            parts = path.relative_to(start).parts
        except ValueError as exc:
            raise PermissionError(f"Path escaped HOST_WORKSPACE_DIR: {path}") from exc

    current = start
    for part in parts:
        current = current / part
        try:
            if current.is_symlink():
                raise PermissionError(f"Symlink paths are not allowed for host file operations: {current}")
        except OSError as exc:
            raise PermissionError(f"Unable to validate path component: {current}") from exc
        if not current.exists():
            break


def resolve_host_path(
    user_path: Optional[str],
    *,
    must_exist: bool = False,
    expect_directory: Optional[bool] = None,
    allow_symlinks: bool = False,
) -> Path:
    """Resolve a user path under the configured host workspace policy.

    Boundary checks are performed on both the lexical path and resolved path.
    Public host file operations reject symlink components by default.
    """
    lexical = _lexical_absolute_path(user_path)
    _assert_workspace_boundary(lexical, user_path)
    if not allow_symlinks:
        _assert_no_symlink_components(lexical)

    resolved = lexical.resolve(strict=False)
    _assert_workspace_boundary(resolved, user_path)

    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"Path not found: {resolved}")
    if expect_directory is True and resolved.exists() and not resolved.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {resolved}")
    if expect_directory is False and resolved.exists() and not resolved.is_file():
        raise ValueError(f"Path is not a regular file: {resolved}")
    return resolved


def display_host_path(path: Path, *, resolve: bool = True) -> str:
    """Prefer a workspace-relative path in public responses.

    ``resolve=False`` is used for directory entries so symlink targets are not
    followed or exposed as absolute external paths.
    """
    base_dir = host_workspace_dir()
    candidate = path.resolve(strict=False) if resolve else Path(os.path.abspath(path))
    try:
        return str(candidate.relative_to(base_dir)) or "."
    except ValueError:
        return str(candidate)
