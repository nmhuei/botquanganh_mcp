from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Optional

import app.config


def host_workspace_dir() -> Path:
    """Return the configured host workspace as an absolute path."""
    return app.config.HOST_WORKSPACE_DIR.resolve()


def host_default_dir() -> Path:
    """Return the default working directory as an absolute path."""
    base_dir = host_workspace_dir()
    default_dir = app.config.HOST_DEFAULT_DIR.resolve()
    if app.config.HOST_RESTRICT_TO_WORKSPACE:
        try:
            default_dir.relative_to(base_dir)
            return default_dir
        except ValueError:
            return base_dir
    return default_dir


def host_read_scopes() -> tuple[Path, ...]:
    """Roots a resolved path may live in for read operations.

    Unset keys track the *current* HOST_WORKSPACE_DIR instead of the value
    captured at import time, so overriding the workspace in-process (tests,
    reloads) keeps the fallback coherent.
    """
    scopes: list[Path] = []
    if app.config.HOST_READ_SCOPE_SET:
        scopes.append(app.config.HOST_READ_SCOPE)
    if app.config.HOST_WRITE_SCOPE_SET:
        scopes.append(app.config.HOST_WRITE_SCOPE)
    return tuple(scopes) if scopes else (host_workspace_dir(),)


def host_write_scope() -> Path:
    """The single root a resolved path must live in for write operations."""
    if app.config.HOST_WRITE_SCOPE_SET:
        return app.config.HOST_WRITE_SCOPE
    return host_workspace_dir()


def _scoped_permissions_enabled() -> bool:
    """True once the operator opts into any Wave 1A scope setting.

    With every new key unset (the default) this is False and path checks run
    the exact legacy workspace-boundary logic.
    """
    return bool(
        app.config.HOST_READ_SCOPE_SET
        or app.config.HOST_WRITE_SCOPE_SET
        or app.config.HOST_READ_DENY_GLOBS
    )


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _path_matches_deny_globs(path: Path, roots: tuple[Path, ...]) -> bool:
    """Match ``path`` against HOST_READ_DENY_GLOBS.

    A pattern matches when it matches the absolute path string, or — for
    relative patterns such as ``secrets/*`` — the path relative to one of the
    scope roots that contains it.
    """
    for pattern in app.config.HOST_READ_DENY_GLOBS:
        expanded = os.path.expanduser(pattern)
        if fnmatch.fnmatch(str(path), expanded):
            return True
        for root in roots:
            try:
                relative = path.relative_to(root)
            except ValueError:
                continue
            if fnmatch.fnmatch(str(relative), expanded):
                return True
    return False


def _assert_scope_boundary(
    path: Path,
    user_path: Optional[str],
    *,
    mode: str,
) -> None:
    """Enforce mode-aware scopes plus deny globs for an opted-in operator."""
    if mode == "write":
        allowed_roots: tuple[Path, ...] = (host_write_scope(),)
        label = "HOST_WRITE_SCOPE"
    else:
        allowed_roots = host_read_scopes()
        label = "HOST_READ_SCOPE"
    if not any(_is_under(path, root) for root in allowed_roots):
        raise PermissionError(
            f"Access denied. Path '{user_path}' is outside {label} "
            f"('{allowed_roots[0]}')."
        )
    if _path_matches_deny_globs(path, allowed_roots):
        raise PermissionError(
            f"Access denied. Path '{user_path}' matches HOST_READ_DENY_GLOBS."
        )


def _scope_walk_bounds(path: Path) -> tuple[Path, tuple[str, ...]]:
    """Pick the deepest configured scope root containing ``path`` to walk from."""
    containing = [
        root for root in (*host_read_scopes(), host_workspace_dir())
        if _is_under(path, root)
    ]
    start = max(containing, key=lambda root: len(root.parts)) if containing else Path(path.anchor)
    if start == Path(path.anchor):
        parts = path.parts[1:]
    else:
        parts = path.relative_to(start).parts
    return start, parts


def _lexical_absolute_path(user_path: Optional[str]) -> Path:
    default_dir = host_default_dir()
    workspace_dir = host_workspace_dir()
    raw = Path(user_path or ".").expanduser()
    if raw.is_absolute():
        candidate = raw
    elif (default_dir / raw).exists():
        candidate = default_dir / raw
    elif (workspace_dir / raw).exists():
        candidate = workspace_dir / raw
    else:
        candidate = default_dir / raw
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


def _assert_no_symlink_components_from(start: Path, parts: tuple[str, ...]) -> None:
    """Reject existing symlink components below ``start`` before an operation.

    Final file operations also use ``O_NOFOLLOW`` where available. This
    component check prevents normal symlink traversal and the no-follow open
    protects the final component from being swapped between validation/open.
    """
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


def _assert_no_symlink_components(path: Path) -> None:
    if not app.config.HOST_RESTRICT_TO_WORKSPACE:
        start = Path(path.anchor)
        parts = path.parts[1:]
    else:
        start = host_workspace_dir()
        try:
            parts = path.relative_to(start).parts
        except ValueError as exc:
            raise PermissionError(f"Path escaped HOST_WORKSPACE_DIR: {path}") from exc

    _assert_no_symlink_components_from(start, parts)


def resolve_host_path(
    user_path: Optional[str],
    *,
    must_exist: bool = False,
    expect_directory: Optional[bool] = None,
    allow_symlinks: bool = False,
    mode: str = "read",
) -> Path:
    """Resolve a user path under the configured host workspace policy.

    Boundary checks are performed on both the lexical path and resolved path.
    Public host file operations reject symlink components by default.

    ``mode`` selects which configured scope applies: write operations require
    the path under HOST_WRITE_SCOPE, read operations accept HOST_READ_SCOPE or
    HOST_WRITE_SCOPE. When none of the scope keys is set (the default) the
    legacy single-workspace behavior is preserved exactly.
    """
    if mode not in ("read", "write"):
        raise ValueError(f"Unknown path access mode: {mode!r}")

    lexical = _lexical_absolute_path(user_path)
    if _scoped_permissions_enabled():
        _assert_scope_boundary(lexical, user_path, mode=mode)
        if not allow_symlinks:
            _assert_no_symlink_components_from(*_scope_walk_bounds(lexical))

        resolved = lexical.resolve(strict=False)
        _assert_scope_boundary(resolved, user_path, mode=mode)
    else:
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
