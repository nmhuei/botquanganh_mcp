from __future__ import annotations

import fcntl
import itertools
import os
import stat
import time
import uuid
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
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _open_regular_file(path: Path, flags: int, mode: int = 0o666) -> int:
    fd = os.open(path, flags | _NOFOLLOW, mode)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError(f"Path is not a regular file: {path}")
        return fd
    except Exception:
        os.close(fd)
        raise


def _write_all(fd: int, raw: bytes) -> None:
    view = memoryview(raw)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("Unable to complete file write.")
        view = view[written:]


def _read_up_to(fd: int, limit: int) -> bytes:
    chunks: list[bytes] = []
    remaining = limit
    while remaining > 0:
        chunk = os.read(fd, min(remaining, 1024 * 1024))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _fsync_directory(directory: Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write(path: Path, raw: bytes, *, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = 0o666
    try:
        existing = path.lstat()
        if stat.S_ISLNK(existing.st_mode):
            raise PermissionError(f"Refusing to replace symlink: {path}")
        if not stat.S_ISREG(existing.st_mode):
            raise ValueError(f"Path is not a regular file: {path}")
        existing_mode = stat.S_IMODE(existing.st_mode)
    except FileNotFoundError:
        pass

    temp = path.parent / f".{path.name}.bqa-tmp-{os.getpid()}-{uuid.uuid4().hex}"
    fd = -1
    try:
        fd = _open_regular_file(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, existing_mode)
        _write_all(fd, raw)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        if overwrite:
            os.replace(temp, path)
        else:
            os.link(temp, path, follow_symlinks=False)
            temp.unlink()
        _fsync_directory(path.parent)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _directory_sort_key(path: Path) -> tuple[bool, str]:
    try:
        is_directory = stat.S_ISDIR(path.lstat().st_mode)
    except OSError:
        is_directory = False
    return (not is_directory, path.name.lower())


def list_directory(path: str = ".", *, max_entries: int = 500) -> dict[str, Any]:
    resolved = resolve_host_path(path, must_exist=True, expect_directory=True)
    max_entries = max(1, min(int(max_entries), 2000))
    selected = list(
        itertools.islice(sorted(resolved.iterdir(), key=_directory_sort_key), max_entries + 1)
    )
    truncated = len(selected) > max_entries
    items: list[dict[str, Any]] = []
    for item in selected[:max_entries]:
        try:
            item_stat = item.lstat()
            is_symlink = stat.S_ISLNK(item_stat.st_mode)
            is_directory = stat.S_ISDIR(item_stat.st_mode)
            items.append(
                {
                    "name": item.name,
                    "path": display_host_path(item, resolve=False),
                    "is_directory": is_directory,
                    "is_symlink": is_symlink,
                    "size_bytes": 0 if is_directory else item_stat.st_size,
                    "modified_ns": item_stat.st_mtime_ns,
                }
            )
        except OSError as exc:
            items.append(
                {
                    "name": item.name,
                    "path": display_host_path(item, resolve=False),
                    "error": str(exc),
                }
            )
    return {
        "ok": True,
        "path": display_host_path(resolved),
        "items": items,
        "truncated": truncated,
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
    fd = _open_regular_file(resolved, os.O_RDONLY)
    try:
        file_size = os.fstat(fd).st_size
        raw = _read_up_to(fd, limit + 1)
    finally:
        os.close(fd)
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


def _validate_write_size(content: str) -> tuple[bytes, int]:
    raw = content.encode("utf-8")
    size = len(raw)
    if size > app.config.MAX_SINGLE_FILE_BYTES:
        raise ValueError(
            f"Content exceeds MAX_SINGLE_FILE_BYTES: {size} > "
            f"{app.config.MAX_SINGLE_FILE_BYTES}"
        )
    return raw, size


def write_text_file(
    path: str,
    content: str,
    *,
    overwrite: bool = True,
    create_parents: bool = True,
) -> dict[str, Any]:
    raw, size = _validate_write_size(content)
    resolved = resolve_host_path(path, mode="write")
    if resolved.exists() and not resolved.is_file():
        raise ValueError(f"Path is not a regular file: {resolved}")
    if resolved.exists() and not overwrite:
        raise FileExistsError(f"File already exists: {resolved}")
    if create_parents:
        resolved.parent.mkdir(parents=True, exist_ok=True)
    elif not resolved.parent.exists():
        raise FileNotFoundError(f"Parent directory does not exist: {resolved.parent}")
    existed = resolved.exists()
    _atomic_write(resolved, raw, overwrite=overwrite)
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
    resolved = resolve_host_path(
        path, must_exist=True, expect_directory=False, mode="write"
    )
    # Crash-atomic swap instead of truncate-in-place: the target is replaced
    # via os.replace() from a fully fsynced temp file in the same directory,
    # so a SIGKILL at any instant can never leave it truncated. The flock on
    # the open target serializes concurrent writers; because a swap swaps the
    # inode, a contender that opened the old inode revalidates and reopens.
    max_attempts = 32
    for _attempt in range(max_attempts):
        fd = _open_regular_file(resolved, os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            live = os.stat(resolved)
            held = os.fstat(fd)
            if (held.st_dev, held.st_ino) != (live.st_dev, live.st_ino):
                # The file was swapped after our open; retry on newest inode.
                continue
            file_size = held.st_size
            if file_size > app.config.MAX_SINGLE_FILE_BYTES:
                raise ValueError(
                    f"File exceeds MAX_SINGLE_FILE_BYTES: {file_size} > "
                    f"{app.config.MAX_SINGLE_FILE_BYTES}"
                )
            raw = _read_up_to(fd, file_size + 1)
            content = raw.decode("utf-8")
            count = content.count(old)
            if count == 0:
                raise ValueError("Target text was not found.")
            if expected_count >= 0 and count != expected_count:
                raise ValueError(f"Expected {expected_count} occurrence(s), found {count}.")
            updated = content.replace(old, new)
            updated_raw, _size = _validate_write_size(updated)
            _atomic_write(resolved, updated_raw, overwrite=True)
        finally:
            os.close(fd)
        break
    else:
        raise OSError(f"File kept changing during replacement: {resolved}")
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
    raw, size = _validate_write_size(content)
    resolved = resolve_host_path(path, mode="write")
    if resolved.exists() and not resolved.is_file():
        raise ValueError(f"Path is not a regular file: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    fd = _open_regular_file(resolved, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        current_size = os.fstat(fd).st_size
        final_size = current_size + size
        if final_size > app.config.MAX_SINGLE_FILE_BYTES:
            raise ValueError(
                f"Append would exceed MAX_SINGLE_FILE_BYTES: {final_size} > "
                f"{app.config.MAX_SINGLE_FILE_BYTES}"
            )
        _write_all(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    log_audit_event(
        "HOST_APPEND_FILE",
        {"path": str(resolved), "appended_bytes": size},
    )
    return {
        "ok": True,
        "path": display_host_path(resolved),
        "appended_bytes": size,
        "file_size_bytes": final_size,
    }


def make_directory(path: str, *, parents: bool = True) -> dict[str, Any]:
    resolved = resolve_host_path(path, mode="write")
    resolved.mkdir(parents=parents, exist_ok=True)
    log_audit_event("HOST_MKDIR", {"path": str(resolved)})
    return {"ok": True, "path": display_host_path(resolved)}


def search_text(
    query: str,
    *,
    path: str = ".",
    case_sensitive: bool = False,
    max_results: int = 100,
    deadline_seconds: Optional[float] = None,
) -> dict[str, Any]:
    if not query:
        raise ValueError("query must not be empty")
    root = resolve_host_path(path, must_exist=True, expect_directory=True)
    max_results = max(1, min(int(max_results), 500))
    if deadline_seconds is None:
        deadline_seconds = app.config.SEARCH_TEXT_DEADLINE_SECONDS
    deadline_seconds = max(0.0, float(deadline_seconds))
    started = time.monotonic()
    needle = query if case_sensitive else query.lower()
    results: list[dict[str, Any]] = []
    scanned_files = 0
    deadline_exceeded = False

    def _out_of_time() -> bool:
        return time.monotonic() - started >= deadline_seconds

    for current_root, dirs, files in os.walk(root, followlinks=False):
        if _out_of_time():
            deadline_exceeded = True
            break
        current_path = Path(current_root)
        dirs[:] = [
            directory
            for directory in dirs
            if directory not in _EXCLUDED_DIRS
            and not (current_path / directory).is_symlink()
        ]
        stop_walk = False
        for filename in files:
            if _out_of_time():
                deadline_exceeded = True
                stop_walk = True
                break
            file_path = current_path / filename
            try:
                file_stat = file_path.lstat()
                if stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode):
                    continue
                if file_stat.st_size > app.config.MAX_SINGLE_FILE_BYTES:
                    continue
                fd = _open_regular_file(file_path, os.O_RDONLY)
                scanned_files += 1
                with os.fdopen(fd, "r", encoding="utf-8", errors="ignore") as handle:
                    for line_number, line in enumerate(handle, 1):
                        haystack = line if case_sensitive else line.lower()
                        if needle in haystack:
                            results.append(
                                {
                                    "path": display_host_path(file_path, resolve=False),
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
                                    "deadline_exceeded": False,
                                }
            except (OSError, UnicodeError, ValueError, PermissionError):
                continue
        if stop_walk:
            break

    return {
        "ok": True,
        "query": query,
        "path": display_host_path(root),
        "results": results,
        "scanned_files": scanned_files,
        "truncated": deadline_exceeded,
        "deadline_exceeded": deadline_exceeded,
    }
