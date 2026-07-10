from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import app.config
from app.host.paths import display_host_path, resolve_host_path
from app.logging_audit import log_audit_event


_EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}


def list_directory(path: str = ".", *, max_entries: int = 500) -> dict[str, Any]:
    resolved = resolve_host_path(path, must_exist=True, expect_directory=True)
    max_entries = max(1, min(int(max_entries), 2000))
    items: list[dict[str, Any]] = []
    for item in sorted(resolved.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        try:
            stat = item.stat()
            items.append(
                {
                    "name": item.name,
                    "path": display_host_path(item),
                    "is_directory": item.is_dir(),
                    "is_symlink": item.is_symlink(),
                    "size_bytes": 0 if item.is_dir() else stat.st_size,
                    "modified_ns": stat.st_mtime_ns,
                }
            )
        except OSError as exc:
            items.append(
                {
                    "name": item.name,
                    "path": display_host_path(item),
                    "error": str(exc),
                }
            )
        if len(items) >= max_entries:
            break
    return {
        "ok": True,
        "path": display_host_path(resolved),
        "items": items,
        "truncated": len(items) >= max_entries,
    }


def read_text_file(
    path: str,
    *,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    max_bytes: Optional[int] = None,
) -> dict[str, Any]:
    resolved = resolve_host_path(path, must_exist=True, expect_directory=False)
    limit = min(
        max(1, int(max_bytes or app.config.MAX_SINGLE_FILE_BYTES)),
        app.config.MAX_SINGLE_FILE_BYTES,
    )
    file_size = resolved.stat().st_size
    with resolved.open("rb") as handle:
        raw = handle.read(limit + 1)
    truncated = len(raw) > limit
    content = raw[:limit].decode("utf-8", errors="replace")
    lines = content.splitlines()
    total_loaded_lines = len(lines)

    if start_line is not None or end_line is not None:
        start = max(1, int(start_line or 1))
        end = max(start, int(end_line or total_loaded_lines))
        content = "\n".join(lines[start - 1 : end])
    else:
        start = 1
        end = total_loaded_lines

    return {
        "ok": True,
        "path": display_host_path(resolved),
        "content": content,
        "file_size_bytes": file_size,
        "loaded_bytes": min(file_size, limit),
        "truncated": truncated,
        "start_line": start,
        "end_line": end,
        "loaded_line_count": total_loaded_lines,
    }


def _validate_write_size(content: str) -> int:
    size = len(content.encode("utf-8"))
    if size > app.config.MAX_SINGLE_FILE_BYTES:
        raise ValueError(
            f"Content exceeds MAX_SINGLE_FILE_BYTES: {size} > "
            f"{app.config.MAX_SINGLE_FILE_BYTES}"
        )
    return size


def write_text_file(
    path: str,
    content: str,
    *,
    overwrite: bool = True,
    create_parents: bool = True,
) -> dict[str, Any]:
    size = _validate_write_size(content)
    resolved = resolve_host_path(path)
    if resolved.exists() and not resolved.is_file():
        raise ValueError(f"Path is not a regular file: {resolved}")
    if resolved.exists() and not overwrite:
        raise FileExistsError(f"File already exists: {resolved}")
    if create_parents:
        resolved.parent.mkdir(parents=True, exist_ok=True)
    elif not resolved.parent.exists():
        raise FileNotFoundError(f"Parent directory does not exist: {resolved.parent}")
    existed = resolved.exists()
    resolved.write_text(content, encoding="utf-8")
    log_audit_event(
        "HOST_WRITE_FILE",
        {"path": str(resolved), "size_bytes": size, "overwrote": existed},
    )
    return {
        "ok": True,
        "path": display_host_path(resolved),
        "size_bytes": size,
        "overwrote": existed,
    }


def replace_text_in_file(
    path: str,
    old: str,
    new: str,
    *,
    expected_count: int = 1,
) -> dict[str, Any]:
    resolved = resolve_host_path(path, must_exist=True, expect_directory=False)
    content = resolved.read_text(encoding="utf-8")
    count = content.count(old)
    if count == 0:
        raise ValueError("Target text was not found.")
    if expected_count >= 0 and count != expected_count:
        raise ValueError(
            f"Expected {expected_count} occurrence(s), found {count}."
        )
    updated = content.replace(old, new)
    _validate_write_size(updated)
    resolved.write_text(updated, encoding="utf-8")
    log_audit_event(
        "HOST_REPLACE_FILE",
        {"path": str(resolved), "replacement_count": count},
    )
    return {
        "ok": True,
        "path": display_host_path(resolved),
        "replacement_count": count,
    }


def append_text_file(path: str, content: str) -> dict[str, Any]:
    size = _validate_write_size(content)
    resolved = resolve_host_path(path)
    if resolved.exists() and not resolved.is_file():
        raise ValueError(f"Path is not a regular file: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("a", encoding="utf-8") as handle:
        handle.write(content)
    log_audit_event(
        "HOST_APPEND_FILE",
        {"path": str(resolved), "appended_bytes": size},
    )
    return {
        "ok": True,
        "path": display_host_path(resolved),
        "appended_bytes": size,
        "file_size_bytes": resolved.stat().st_size,
    }


def make_directory(path: str, *, parents: bool = True) -> dict[str, Any]:
    resolved = resolve_host_path(path)
    resolved.mkdir(parents=parents, exist_ok=True)
    log_audit_event("HOST_MKDIR", {"path": str(resolved)})
    return {"ok": True, "path": display_host_path(resolved)}


def search_text(
    query: str,
    *,
    path: str = ".",
    case_sensitive: bool = False,
    max_results: int = 100,
) -> dict[str, Any]:
    if not query:
        raise ValueError("query must not be empty")
    root = resolve_host_path(path, must_exist=True, expect_directory=True)
    max_results = max(1, min(int(max_results), 500))
    needle = query if case_sensitive else query.lower()
    results: list[dict[str, Any]] = []
    scanned_files = 0

    for current_root, dirs, files in os.walk(root):
        dirs[:] = [
            directory
            for directory in dirs
            if directory not in _EXCLUDED_DIRS
        ]
        for filename in files:
            file_path = Path(current_root) / filename
            try:
                if file_path.is_symlink() or file_path.stat().st_size > app.config.MAX_SINGLE_FILE_BYTES:
                    continue
                scanned_files += 1
                with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
                    for line_number, line in enumerate(handle, 1):
                        haystack = line if case_sensitive else line.lower()
                        if needle in haystack:
                            results.append(
                                {
                                    "path": display_host_path(file_path),
                                    "line_number": line_number,
                                    "line": line.rstrip("\n")[:1000],
                                }
                            )
                            if len(results) >= max_results:
                                return {
                                    "ok": True,
                                    "query": query,
                                    "path": display_host_path(root),
                                    "results": results,
                                    "scanned_files": scanned_files,
                                    "truncated": True,
                                }
            except (OSError, UnicodeError):
                continue

    return {
        "ok": True,
        "query": query,
        "path": display_host_path(root),
        "results": results,
        "scanned_files": scanned_files,
        "truncated": False,
    }
