"""Deadline-safe ripgrep and secure Python fallback engines."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import time
from pathlib import Path
from typing import Any

from app import config
from app.host.paths import _path_matches_deny_globs, display_host_path, host_read_scopes
from app.search_models import SearchCounters, SearchEngine, SearchLimitReason, SearchOutcome
from app.search_runtime import deadline_from_timeout, reap_process, terminate_process_group
from app import search_runtime


_DEFAULT_IGNORES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "build",
    "dist",
    "journal.jsonl",
    "journal.jsonl.1",
    "meta.json",
    ".last_session",
}

def _stderr_cap_bytes() -> int:
    """Bound captured stderr using configured text limits."""
    try:
        return max(1, int(config.WORKSPACE_SEARCH_MAX_LINE_CHARS))
    except (AttributeError, TypeError, ValueError):
        from app.cli.config_view import DEFAULTS as _defaults

        return max(1, int(_defaults["WORKSPACE_SEARCH_MAX_LINE_CHARS"]))


def truncate_line(text: str) -> str:
    """Bound one returned line preview using configured chars."""
    try:
        limit = int(config.WORKSPACE_SEARCH_MAX_LINE_CHARS)
    except (AttributeError, TypeError, ValueError):
        try:
            from app.cli.config_view import DEFAULTS as _defaults

            limit = int(_defaults["WORKSPACE_SEARCH_MAX_LINE_CHARS"])
        except (AttributeError, TypeError, ValueError, KeyError):
            return text
    if len(text) <= limit:
        return text
    return text[:limit] + "...[line truncated]"


def _should_skip_name(path: Path, include_hidden: bool) -> bool:
    if path.name in _DEFAULT_IGNORES:
        return True
    for part in path.parts:
        if part in _DEFAULT_IGNORES:
            return True
        if not include_hidden and part.startswith(".") and part not in {".", ".."}:
            return True
    return False


def _deny_excluded_args() -> list[str]:
    args: list[str] = []
    for pattern in list(getattr(config, "HOST_READ_DENY_GLOBS", []) or []):
        cleaned = str(pattern).strip()
        if cleaned:
            args.extend(["--glob", f"!{cleaned}"])
    return args


def _build_ripgrep_argv(
    root: Path, query: str, regex: bool, case_sensitive: bool, include_hidden: bool
) -> list[str]:
    argv = ["rg", "--json", "--no-heading", "--no-config"]
    argv.extend(["--max-filesize", str(int(config.MAX_SINGLE_FILE_BYTES))])
    argv.extend(["-e", query] if regex else ["-F", "-e", query])
    argv.append("-s" if case_sensitive else "-i")
    if include_hidden:
        argv.append("--hidden")
    for ignore in sorted(_DEFAULT_IGNORES):
        argv.extend(["--glob", f"!{ignore}/**", "--glob", f"!{ignore}"])
    argv.extend(_deny_excluded_args())
    argv.extend(["--", str(root)])
    return argv


def _parse_rg_match_line(line: str) -> dict[str, Any] | None:
    if '"type":"match"' not in line and '"type": "match"' not in line:
        return None
    try:
        event = json.loads(line)
    except (ValueError, TypeError):
        return None
    if not isinstance(event, dict) or event.get("type") != "match":
        return None
    data = event.get("data") or {}
    path_text = str((data.get("path") or {}).get("text", ""))
    text = str((data.get("lines") or {}).get("text", "")).rstrip("\r\n")
    return {
        "file": path_text,
        "line": data.get("line_number"),
        "text": truncate_line(text),
    }


def _search_deadline_seconds() -> float:
    """Return the configured wall-clock deadline for search engines."""
    try:
        return max(0.0, float(config.SEARCH_TEXT_DEADLINE_SECONDS))
    except (AttributeError, TypeError, ValueError):
        from app.cli.config_view import DEFAULTS as _defaults

        return max(0.0, float(_defaults["SEARCH_TEXT_DEADLINE_SECONDS"]))


def _scanned_limits() -> tuple[int, int]:
    """Return configured scanned-file and scanned-byte ceilings."""
    try:
        max_files = int(config.WORKSPACE_SEARCH_MAX_SCANNED_FILES)
    except (AttributeError, TypeError, ValueError):
        from app.cli.config_view import DEFAULTS as _defaults

        max_files = int(_defaults["WORKSPACE_SEARCH_MAX_SCANNED_FILES"])
    try:
        max_bytes = int(config.WORKSPACE_SEARCH_MAX_SCANNED_BYTES)
    except (AttributeError, TypeError, ValueError):
        from app.cli.config_view import DEFAULTS as _defaults

        max_bytes = int(_defaults["WORKSPACE_SEARCH_MAX_SCANNED_BYTES"])
    return (max(1, max_files), max(1, max_bytes))


def _max_single_file_bytes() -> int:
    """Return the per-file scan cap from configuration."""
    try:
        return max(1, int(config.MAX_SINGLE_FILE_BYTES))
    except (AttributeError, TypeError, ValueError):
        from app.cli.config_view import DEFAULTS as _defaults

        return max(1, int(_defaults["MAX_SINGLE_FILE_BYTES"]))


def _inventory_scan_bounds(
    root: Path, include_hidden: bool, deadline: float | None
) -> tuple[int, int, SearchLimitReason | None]:
    """Bound total files and bytes with stat-only walk before ripgrep.

    Ripgrep emits only a final summary for match-free scans. This walk
    proves totals fit ceilings before starting rg. Over-limit roots fall
    back to the bounded Python walker.
    """
    max_files, max_bytes = _scanned_limits()
    max_single = _max_single_file_bytes()
    try:
        roots = host_read_scopes()
    except (OSError, ValueError, AttributeError):
        roots = ()
    count = 0
    total = 0
    try:
        walker = os.walk(root, followlinks=False)
    except OSError:
        return (0, 0, None)
    for current_dir, dirs, files in walker:
        if deadline is not None and time.monotonic() >= deadline:
            return (count, total, SearchLimitReason.DEADLINE)
        current = Path(current_dir)
        kept: list[str] = []
        for name in dirs:
            candidate = current / name
            try:
                entry_stat = candidate.lstat()
            except OSError:
                continue
            if not stat.S_ISDIR(entry_stat.st_mode):
                continue
            if stat.S_ISLNK(entry_stat.st_mode):
                continue
            if _should_skip_name(candidate, include_hidden):
                continue
            kept.append(name)
        dirs[:] = kept
        for filename in files:
            if deadline is not None and time.monotonic() >= deadline:
                return (count, total, SearchLimitReason.DEADLINE)
            item = current / filename
            if _should_skip_name(item, include_hidden):
                continue
            try:
                resolved = item.resolve(strict=False)
            except OSError:
                continue
            try:
                if _is_denied(item, resolved, root, roots):
                    continue
            except (OSError, ValueError):
                continue
            try:
                entry_stat = item.lstat()
            except OSError:
                continue
            if stat.S_ISLNK(entry_stat.st_mode) or not stat.S_ISREG(entry_stat.st_mode):
                continue
            if entry_stat.st_size > max_single:
                continue
            count += 1
            total += min(entry_stat.st_size, max_single)
            if count > max_files:
                return (count, total, SearchLimitReason.SCANNED_FILES)
            if total > max_bytes:
                return (count, total, SearchLimitReason.SCANNED_BYTES)
    return (count, total, None)


def _drain_stderr_loop(proc: subprocess.Popen, holder: dict[str, str], cap: int) -> None:
    """Continuously drain stderr so sustained output cannot block ripgrep."""
    buffered: list[str] = []
    try:
        stream = getattr(proc, "stderr", None)
        if stream is None or not hasattr(stream, "read"):
            return
        kept = 0
        while True:
            try:
                chunk = stream.read(cap)
            except (OSError, ValueError, AttributeError, TypeError):
                break
            if not chunk:
                break
            if isinstance(chunk, bytes):
                text = chunk.decode("utf-8", errors="replace")
            else:
                text = str(chunk or "")
            if kept < cap:
                buffered.append(text[: max(0, cap - kept)])
                kept += len(text)
            # Discard beyond cap but keep reading to avoid pipe blockage.
    except (OSError, ValueError, AttributeError, TypeError):
        return
    finally:
        try:
            holder["text"] = "".join(buffered)[:cap]
        except (AttributeError, TypeError):
            pass


def _start_stderr_drain(proc: subprocess.Popen) -> tuple[Any, dict[str, str]]:
    """Drain stderr in background so a full pipe cannot block ripgrep."""
    holder: dict[str, str] = {"text": ""}
    cap = _stderr_cap_bytes()

    def _drain() -> None:
        _drain_stderr_loop(proc, holder, cap)

    try:
        import threading as _threading

        thread = _threading.Thread(target=_drain, name="bqa-rg-stderr", daemon=True)
        thread.start()
        return thread, holder
    except (OSError, ValueError, RuntimeError):
        return None, holder


def _finish_stderr_drain(thread: Any, holder: dict[str, str]) -> str:
    """Wait briefly for stderr drain and return bounded text."""
    if thread is None:
        return str(holder.get("text") or "")
    try:
        from app.search_runtime import search_reap_timeout as _reap_timeout

        timeout = _reap_timeout()
        if timeout is None:
            thread.join()
        else:
            thread.join(timeout=float(timeout))
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return str(holder.get("text") or "")


def _poll_slice_seconds(timeout: float | None) -> float:
    """Return a bounded select slice derived from configured queue timeout."""
    try:
        configured = float(config.WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS)
    except (AttributeError, TypeError, ValueError):
        from app.cli.config_view import DEFAULTS as _defaults

        configured = float(_defaults["WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS"])
    if timeout is None:
        return max(0.0, configured)
    return max(0.0, min(configured, timeout))


def _stdout_ready(stream: Any, timeout: float | None) -> bool:
    """Return True when stdout has data or readiness cannot be probed."""
    try:
        fileno = stream.fileno()
    except (OSError, ValueError, AttributeError):
        return True
    try:
        import select as _select

        readable, _, _ = _select.select([fileno], [], [], _poll_slice_seconds(timeout))
        return bool(readable)
    except (OSError, ValueError, TypeError):
        return True


def _parse_rg_summary_line(line: str) -> tuple[int | None, int | None]:
    """Extract (searches, bytes_searched) from an rg JSON summary event."""
    if '"type"' not in line or "summary" not in line:
        return (None, None)
    try:
        event = json.loads(line)
    except (ValueError, TypeError):
        return (None, None)
    if not isinstance(event, dict) or event.get("type") != "summary":
        return (None, None)
    try:
        stats = (event.get("data") or {}).get("stats") or {}
        searches = stats.get("searches")
        searched = stats.get("bytes_searched")
        return (
            int(searches) if searches is not None else None,
            int(searched) if searched is not None else None,
        )
    except (TypeError, ValueError):
        return (None, None)


def _error_outcome(message: str, code: str = "INTERNAL_ERROR") -> SearchOutcome:
    return SearchOutcome(
        ok=False,
        matches=[],
        total_found=0,
        count_complete=False,
        limit_reason=None,
        counters=SearchCounters(),
        engine=SearchEngine.RIPGREP,
        error={"code": code, "message": message},
    )


def _iter_rg_stream(stream: Any) -> Any:
    """Yield lines from readline streams and simple test iterables."""
    if hasattr(stream, "readline"):
        while True:
            try:
                line = stream.readline()
            except (OSError, ValueError, AttributeError):
                return
            if not line:
                return
            yield line
        return
    try:
        for line in stream:
            yield line
    except (OSError, ValueError, AttributeError):
        return


def _consume_rg_stream(
    proc: Any,
    stream: Any,
    deadline: float | None,
    max_matches: int,
    max_work_matches: int,
    max_files: int,
    max_bytes: int,
    exact_count: bool,
) -> dict[str, Any]:
    """Read rg JSON with absolute deadline and scanned budgets."""
    matches: list[dict[str, Any]] = []
    total = 0
    limit_reason: SearchLimitReason | None = None
    seen_files: set[str] = set()
    matched_bytes = 0
    summary_files: int | None = None
    summary_bytes: int | None = None
    state = {"iter": _iter_rg_stream(stream), "pending": None}
    while True:
        if deadline is not None and time.monotonic() >= deadline:
            limit_reason = SearchLimitReason.DEADLINE
            break
        remaining = (deadline - time.monotonic()) if deadline is not None else None
        if remaining is not None and remaining <= 0:
            limit_reason = SearchLimitReason.DEADLINE
            break
        if not _stdout_ready(stream, remaining):
            try:
                exited = proc.poll() is not None
            except (OSError, ValueError, AttributeError):
                exited = False
            if exited:
                break
            continue
        try:
            line = next(state["iter"])
        except StopIteration:
            break
        except (OSError, ValueError):
            break
        if not isinstance(line, str) or not line:
            try:
                exited = proc.poll() is not None
            except (OSError, ValueError, AttributeError):
                exited = False
            if exited:
                break
            continue
        if '"type"' in line and "summary" in line:
            files, nbytes = _parse_rg_summary_line(line)
            if files is not None:
                summary_files = files
            if nbytes is not None:
                summary_bytes = nbytes
            continue
        if '"type":"match"' not in line and '"type": "match"' not in line:
            continue
        if len(matches) >= max_matches and not exact_count:
            total += 1
            limit_reason = SearchLimitReason.RESULT_CAP
            break
        total += 1
        if len(matches) < max_matches:
            parsed = _parse_rg_match_line(line)
            if parsed is not None:
                matches.append(parsed)
                seen_files.add(str(parsed.get("file") or ""))
                matched_bytes += len(str(parsed.get("text") or "").encode("utf-8"))
        if len(seen_files) > max_files or (summary_files or 0) > max_files:
            limit_reason = SearchLimitReason.SCANNED_FILES
            break
        if matched_bytes > max_bytes or (summary_bytes or 0) > max_bytes:
            limit_reason = SearchLimitReason.SCANNED_BYTES
            break
        if max_work_matches > 0 and total >= max_work_matches:
            limit_reason = SearchLimitReason.WORK_MATCHES
            break
        if deadline is not None and time.monotonic() >= deadline:
            limit_reason = SearchLimitReason.DEADLINE
            break
    if limit_reason is None and deadline is not None and time.monotonic() >= deadline:
        limit_reason = SearchLimitReason.DEADLINE
    return {
        "matches": matches, "total": total, "limit_reason": limit_reason,
        "seen_files": len(seen_files), "matched_bytes": matched_bytes,
        "summary_files": summary_files, "summary_bytes": summary_bytes,
    }


def _apply_rg_scanned_posthoc(
    result: dict[str, Any], max_files: int, max_bytes: int
) -> SearchLimitReason | None:
    """Enforce scanned ceilings from rg summary stats when present."""
    existing = result.get("limit_reason")
    if existing is not None:
        return existing
    summary_files = result.get("summary_files")
    summary_bytes = result.get("summary_bytes")
    if isinstance(summary_files, int) and summary_files > max_files:
        return SearchLimitReason.SCANNED_FILES
    if isinstance(summary_bytes, int) and summary_bytes > max_bytes:
        return SearchLimitReason.SCANNED_BYTES
    return None


def run_ripgrep_search(
    root: Path,
    query: str,
    regex: bool,
    case_sensitive: bool,
    max_matches: int,
    include_hidden: bool,
    max_work_matches: int,
    exact_count: bool = False,
) -> SearchOutcome:
    """Run ripgrep with absolute deadline, stderr drain, and group cleanup."""
    deadline = deadline_from_timeout(_search_deadline_seconds())
    max_files, max_bytes = _scanned_limits()
    _, _, inventory_reason = _inventory_scan_bounds(root, include_hidden, deadline)
    if inventory_reason is not None:
        return run_python_search(
            root, query, regex, case_sensitive, max_matches,
            include_hidden, max_work_matches, exact_count,
        )
    argv = _build_ripgrep_argv(root, query, regex, case_sensitive, include_hidden)
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except OSError:
        return run_python_search(
            root, query, regex, case_sensitive, max_matches,
            include_hidden, max_work_matches, exact_count,
        )
    sensitive = {"matches": [], "total": 0, "limit_reason": None}
    stderr_thread, stderr_holder = _start_stderr_drain(proc)
    early_exit = False
    try:
        stream = proc.stdout
        if stream is None:
            remaining = (deadline - time.monotonic()) if deadline is not None else None
            try:
                if remaining is None:
                    proc.wait()
                else:
                    proc.wait(timeout=max(0.0, remaining))
            except TypeError:
                proc.wait()
            except (subprocess.TimeoutExpired, OSError, ValueError):
                sensitive["limit_reason"] = SearchLimitReason.DEADLINE
                early_exit = True
        else:
            sensitive = _consume_rg_stream(
                proc, stream, deadline, max_matches,
                int(max_work_matches or 0), max_files, max_bytes, exact_count,
            )
            if sensitive.get("limit_reason") is not None:
                early_exit = True
        if sensitive.get("limit_reason") is None:
            posthoc = _apply_rg_scanned_posthoc(sensitive, max_files, max_bytes)
            if posthoc is not None:
                sensitive["limit_reason"] = posthoc
                early_exit = True
        if early_exit:
            terminate_process_group(proc)
    finally:
        try:
            stream_obj = getattr(proc, "stdout", None)
            if stream_obj is not None:
                stream_obj.close()
        except (OSError, ValueError, AttributeError):
            pass
        try:
            reap_process(proc)
        except (OSError, ValueError, AttributeError, TypeError):
            pass
    stderr_text = _finish_stderr_drain(stderr_thread, stderr_holder)
    limit_reason = sensitive.get("limit_reason")
    total = int(sensitive.get("total") or 0)
    matches = list(sensitive.get("matches") or [])
    count_complete = limit_reason is None
    code = getattr(proc, "returncode", None)
    if limit_reason is not None:
        pass
    elif code not in (0, 1, None):
        message = stderr_text.strip() or f"ripgrep exited with code {code}."
        lowered = message.lower()
        if "unrecognized" in lowered or "regex" in lowered or "pattern" in lowered:
            return _error_outcome(message, code="INVALID_ARGUMENT")
        return _error_outcome(message)
    if limit_reason is None and code == 1:
        count_complete = True
    scanned_files = int(sensitive.get("summary_files") or sensitive.get("seen_files") or 0)
    scanned_bytes = int(sensitive.get("summary_bytes") or sensitive.get("matched_bytes") or 0)
    counters = SearchCounters(
        scanned_files=min(scanned_files, max_files),
        scanned_bytes=min(scanned_bytes, max_bytes),
        candidate_matches=total, returned_matches=len(matches),
    )
    return SearchOutcome(
        ok=True, matches=matches, total_found=total,
        count_complete=count_complete, limit_reason=limit_reason,
        counters=counters, engine=SearchEngine.RIPGREP,
    )


def _is_denied(item: Path, resolved: Path, search_root: Path, roots: tuple[Path, ...]) -> bool:
    """Apply deny globs to absolute and search-relative paths."""
    import fnmatch as _fnmatch

    candidates = tuple(dict.fromkeys((resolved, item.absolute(), search_root)))
    try:
        from app.host.paths import _path_matches_deny_globs as deny_match

        if deny_match(resolved, roots) or deny_match(item.absolute(), roots):
            return True
    except (OSError, ValueError):
        return True
    patterns = list(getattr(config, "HOST_READ_DENY_GLOBS", []) or [])
    for pattern in patterns:
        cleaned = str(pattern).strip()
        if not cleaned:
            continue
        for base in (search_root,):
            try:
                relative = resolved.relative_to(base)
            except ValueError:
                continue
            if _fnmatch.fnmatch(str(relative), cleaned) or _fnmatch.fnmatch(
                resolved.name, cleaned
            ):
                return True
    return False


def _open_regular_nofollow(path: Path) -> int | None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        file_stat = path.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(file_stat.st_mode):
        return None
    try:
        return os.open(path, flags)
    except OSError:
        return None


# Conservative Python fallback regex subset.
#
# Accepted patterns satisfy all rules below. Anything else is rejected with
# INVALID_ARGUMENT when ripgrep is unavailable. The subset keeps per-line
# `re.search` linear on bounded lines so an accepted pattern cannot block
# beyond the configured search deadline.
#
# - Length fits WORKSPACE_SEARCH_MAX_LINE_CHARS.
# - No unescaped group or alternation markers: '(' ')' '|'.
# - No backreferences (`\1` ..) and no lookaround (implied by no parens).
# - At most one quantifier (`?`, `*`, or `+`) is allowed in the full pattern.
# - Bounded `{m,n}` quantifiers are rejected. Character classes count as atoms.
_SAFE_FALLBACK_MAX_QUANTIFIERS = 1


def _fallback_pattern_too_long(query: str) -> bool:
    """Return True when the pattern exceeds the configured line budget."""
    try:
        max_pattern = int(config.WORKSPACE_SEARCH_MAX_LINE_CHARS)
    except (AttributeError, TypeError, ValueError):
        return False
    return len(query) > max_pattern


def _skip_class_end(query: str, start: int) -> int:
    """Return index after a `[...]` class starting at `start`."""
    index = start + 1
    if index < len(query) and query[index] == "^":
        index += 1
    if index < len(query) and query[index] == "]":
        index += 1
    while index < len(query):
        char = query[index]
        if char == "\\":
            index += 2
            continue
        if char == "]":
            return index + 1
        index += 1
    return len(query)


def _match_brace_quantifier(query: str, start: int) -> int:
    """Return end index of `{m,n}` at `start` or `start` when literal."""
    closing = query.find("}", start)
    if closing == -1:
        return start
    inner = query[start + 1 : closing].strip()
    if not inner:
        return start
    parts = inner.split(",")
    if len(parts) > 2:
        return start
    if not all(part.strip().isdigit() or not part.strip() for part in parts):
        return start
    if len(parts) == 1 and not parts[0].strip().isdigit():
        return start
    return closing + 1


def _count_safe_atoms(query: str) -> tuple[int, bool]:
    """Count all quantifiers and detect constructs that can backtrack."""
    quantifiers = 0
    index = 0
    length = len(query)
    while index < length:
        char = query[index]
        if char == "\\":
            if index + 1 >= length:
                return (quantifiers, True)
            if query[index + 1].isdigit():
                return (quantifiers, True)
            index += 2
            continue
        if char == "[":
            index = _skip_class_end(query, index)
            if index < length and query[index] in {"*", "+", "?"}:
                quantifiers += 1
                index += 1
                if index < length and query[index] in {"?", "+"}:
                    index += 1
            elif index < length and query[index] == "{":
                end = _match_brace_quantifier(query, index)
                if end != index:
                    return (quantifiers + 1, True)
            continue
        if char in {"(", ")", "|"}:
            return (quantifiers, True)
        if char in {"*", "+", "?"}:
            quantifiers += 1
            index += 1
            if index < length and query[index] in {"?", "+"}:
                index += 1
            continue
        if char == "{":
            end = _match_brace_quantifier(query, index)
            if end != index:
                return (quantifiers + 1, True)
        index += 1
    return (quantifiers, False)


def _fallback_regex_safety_error(query: str) -> dict[str, str] | None:
    """Validate the conservative safe regex subset for Python fallback."""
    if _fallback_pattern_too_long(query):
        return {
            "code": "INVALID_ARGUMENT",
            "message": "Fallback regex exceeds configured line budget; refine the pattern.",
        }
    quantifiers, forbidden = _count_safe_atoms(query)
    if forbidden or quantifiers > _SAFE_FALLBACK_MAX_QUANTIFIERS:
        return {
            "code": "INVALID_ARGUMENT",
            "message": (
                "Fallback regex is outside the safe subset (no groups, "
                "alternation, backreferences, or multiple quantifiers); "
                "install ripgrep or simplify the pattern."
            ),
        }
    return None


def run_python_search(
    root: Path,
    query: str,
    regex: bool,
    case_sensitive: bool,
    max_matches: int,
    include_hidden: bool,
    max_work_matches: int,
    exact_count: bool = False,
) -> SearchOutcome:
    """Secure traversal fallback with file, byte, match, deadline budgets."""
    deadline = deadline_from_timeout(_search_deadline_seconds())
    max_files, max_bytes = _scanned_limits()
    work_budget = int(max_work_matches or 0)
    if regex:
        safety = _fallback_regex_safety_error(query)
        if safety is not None:
            return SearchOutcome(
                ok=False, matches=[], total_found=0, count_complete=False,
                counters=SearchCounters(), engine=SearchEngine.PYTHON,
                error=safety,
            )
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        matcher = re.compile(query, flags=flags) if regex else None
    except re.error as exc:
        return SearchOutcome(
            ok=False, matches=[], total_found=0, count_complete=False,
            counters=SearchCounters(), engine=SearchEngine.PYTHON,
            error={"code": "INVALID_ARGUMENT", "message": f"Invalid regex: {exc}"},
        )
    needle = query if case_sensitive else query.lower()
    matches: list[dict[str, Any]] = []
    total = 0
    scanned_files = 0
    scanned_bytes = 0
    skipped = 0
    limit_reason: SearchLimitReason | None = None
    count_complete = True
    roots = host_read_scopes()
    outcome = _walk_python_root(
        root, matcher, needle, case_sensitive, max_matches, include_hidden,
        work_budget, exact_count, deadline, max_files, max_bytes, roots,
    )
    return outcome


def _prune_search_dirs(
    current: Path, dirs: list[str], include_hidden: bool
) -> tuple[list[str], int]:
    """Filter walk dirs in place and count skipped special entries."""
    kept: list[str] = []
    skipped = 0
    for name in dirs:
        candidate = current / name
        try:
            entry_stat = candidate.lstat()
        except OSError:
            skipped += 1
            continue
        if not stat.S_ISDIR(entry_stat.st_mode):
            skipped += 1
            continue
        if stat.S_ISLNK(entry_stat.st_mode):
            skipped += 1
            continue
        if _should_skip_name(candidate, include_hidden):
            continue
        kept.append(name)
    dirs[:] = kept
    return kept, skipped


def _resolve_walk_file(
    item: Path, root: Path, roots: tuple[Path, ...]
) -> tuple[Path, os.stat_result] | None:
    """Resolve one walk entry or return None when it must be skipped."""
    try:
        resolved = item.resolve(strict=False)
    except OSError:
        return None
    try:
        if _is_denied(item, resolved, root, roots):
            return None
    except (OSError, ValueError):
        return None
    try:
        entry_stat = item.lstat()
    except OSError:
        return None
    if stat.S_ISLNK(entry_stat.st_mode):
        return None
    if not stat.S_ISREG(entry_stat.st_mode):
        return None
    return (resolved, entry_stat)


def _file_budget_reason(
    scanned_files: int, scanned_bytes: int, max_files: int, max_bytes: int
) -> SearchLimitReason | None:
    """Return the exhausted file or byte budget before opening a file."""
    if scanned_files >= max_files:
        return SearchLimitReason.SCANNED_FILES
    if scanned_bytes >= max_bytes:
        return SearchLimitReason.SCANNED_BYTES
    return None


def _max_single_bytes() -> int:
    """Return per-file scan cap from configuration."""
    return _max_single_file_bytes()


def _process_walk_file(
    item: Path,
    root: Path,
    roots: tuple[Path, ...],
    matcher: re.Pattern | None,
    needle: str,
    case_sensitive: bool,
    matches: list[dict[str, Any]],
    max_matches: int,
    deadline: float | None,
    total: int,
    work_budget: int,
    exact_count: bool,
    scanned_files: int,
    scanned_bytes: int,
    max_files: int,
    max_bytes: int,
) -> tuple[int, int, bool, SearchLimitReason | None, bool]:
    """Scan one file with remaining budgets. Return (found, bytes, stop, reason, skipped)."""
    budget_reason = _file_budget_reason(scanned_files, scanned_bytes, max_files, max_bytes)
    if budget_reason is not None:
        return (0, 0, True, budget_reason, False)
    resolved = _resolve_walk_file(item, root, roots)
    if resolved is None:
        return (0, 0, False, None, True)
    _, entry_stat = resolved
    if entry_stat.st_size > _max_single_bytes():
        return (0, 0, False, None, True)
    found, file_bytes, stop, reason = _scan_one_file(
        item, matcher, needle, case_sensitive, matches, max_matches,
        deadline, total, work_budget, exact_count, scanned_bytes, max_bytes,
    )
    return (found, file_bytes, stop, reason, False)


def _apply_walk_result(
    state: dict[str, Any], found: int, file_bytes: int,
    stop: bool, reason: SearchLimitReason | None, max_matches: int,
    work_budget: int, exact_count: bool, max_bytes: int,
) -> bool:
    """Accumulate one file result and report whether the dir loop must stop."""
    state["scanned_files"] += 1
    state["scanned_bytes"] = min(max_bytes, state["scanned_bytes"] + file_bytes)
    state["total"] += found
    if reason is not None:
        state["limit_reason"] = reason
        state["count_complete"] = False
    if stop:
        return True
    if work_budget > 0 and state["total"] >= work_budget:
        state["limit_reason"] = SearchLimitReason.WORK_MATCHES
        state["count_complete"] = False
        return True
    return False


def _should_stop_walk(
    state: dict[str, Any], work_budget: int, exact_count: bool
) -> bool:
    """Return True when the outer walk must stop after one directory."""
    reason = state.get("limit_reason")
    if reason is None or state.get("count_complete", True):
        return False
    if reason == SearchLimitReason.RESULT_CAP and exact_count:
        return bool(work_budget > 0 and state["total"] >= work_budget)
    return True


def _walk_python_root(
    root: Path, matcher: re.Pattern | None, needle: str, case_sensitive: bool,
    max_matches: int, include_hidden: bool, work_budget: int, exact_count: bool,
    deadline: float | None, max_files: int, max_bytes: int,
    roots: tuple[Path, ...],
) -> SearchOutcome:
    state: dict[str, Any] = {
        "matches": [], "total": 0, "scanned_files": 0, "scanned_bytes": 0,
        "skipped": 0, "limit_reason": None, "count_complete": True,
    }
    for current_dir, dirs, files in os.walk(root, followlinks=False):
        if deadline is not None and time.monotonic() >= deadline:
            state["limit_reason"] = SearchLimitReason.DEADLINE
            state["count_complete"] = False
            break
        current = Path(current_dir)
        _, dir_skipped = _prune_search_dirs(current, dirs, include_hidden)
        state["skipped"] += dir_skipped
        for filename in files:
            if deadline is not None and time.monotonic() >= deadline:
                state["limit_reason"] = SearchLimitReason.DEADLINE
                state["count_complete"] = False
                break
            item = current / filename
            if _should_skip_name(item, include_hidden):
                continue
            found, file_bytes, stop, reason, was_skipped = _process_walk_file(
                item, root, roots, matcher, needle, case_sensitive,
                state["matches"], max_matches, deadline, state["total"],
                work_budget, exact_count, state["scanned_files"],
                state["scanned_bytes"], max_files, max_bytes,
            )
            if was_skipped:
                state["skipped"] += 1
                continue
            if _apply_walk_result(
                state, found, file_bytes, stop, reason, max_matches,
                work_budget, exact_count, max_bytes,
            ):
                break
        if _should_stop_walk(state, work_budget, exact_count):
            break
    counters = SearchCounters(
        scanned_files=min(state["scanned_files"], max_files),
        scanned_bytes=min(state["scanned_bytes"], max_bytes),
        candidate_matches=state["total"],
        returned_matches=len(state["matches"]),
        skipped_special_files=state["skipped"],
    )
    return SearchOutcome(
        ok=True, matches=state["matches"], total_found=state["total"],
        count_complete=state["count_complete"],
        limit_reason=state["limit_reason"],
        counters=counters, engine=SearchEngine.PYTHON,
    )


def _scan_one_file(
    item: Path, matcher: re.Pattern | None, needle: str, case_sensitive: bool,
    matches: list[dict[str, Any]], max_matches: int, deadline: float | None,
    total_so_far: int = 0, work_budget: int = 0, exact_count: bool = False,
    scanned_bytes_so_far: int = 0, max_bytes: int = 0,
) -> tuple[int, int, bool, SearchLimitReason | None]:
    """Scan a file with bounded reads and per-line search budgets."""
    found = 0
    file_bytes = 0
    descriptor = _open_regular_nofollow(item)
    if descriptor is None:
        return 0, 0, False, None
    try:
        file_size = os.fstat(descriptor).st_size
        max_single = _max_single_file_bytes()
        with os.fdopen(descriptor, "rb") as handle:
            line_number = 0
            while True:
                if deadline is not None and time.monotonic() >= deadline:
                    return found, file_bytes, True, SearchLimitReason.DEADLINE
                remaining_total = max_bytes - scanned_bytes_so_far - file_bytes
                remaining_file = max_single - file_bytes
                if remaining_total <= 0 or remaining_file <= 0:
                    if file_bytes >= file_size:
                        return found, file_bytes, False, None
                    return found, file_bytes, True, SearchLimitReason.SCANNED_BYTES
                read_limit = min(remaining_total, remaining_file)
                raw_line = handle.readline(read_limit)
                if not raw_line:
                    return found, file_bytes, False, None
                line_number += 1
                file_bytes += len(raw_line)
                line = raw_line.decode("utf-8", errors="ignore")
                partial_line = (
                    len(raw_line) == read_limit
                    and not raw_line.endswith(b"\n")
                    and file_bytes < file_size
                )
                if b"\x00" in raw_line:
                    return found, file_bytes, False, None
                haystack = line if case_sensitive else line.lower()
                hit = bool(matcher.search(line)) if matcher else (needle in haystack)
                if hit:
                    found += 1
                    if len(matches) >= max_matches and not exact_count:
                        return found, file_bytes, True, SearchLimitReason.RESULT_CAP
                    if len(matches) < max_matches:
                        matches.append({
                            "file": display_host_path(item, resolve=False),
                            "line": line_number,
                            "text": truncate_line(line.rstrip("\r\n")),
                        })
                    if work_budget > 0 and total_so_far + found >= work_budget:
                        return found, file_bytes, True, SearchLimitReason.WORK_MATCHES
                if partial_line:
                    return found, file_bytes, True, SearchLimitReason.SCANNED_BYTES
    except (OSError, ValueError):
        return found, file_bytes, False, None


def _build_path_argv(root: Path, glob_pattern: str, include_hidden: bool) -> list[str]:
    """Build argv for filename listing with deny rules applied."""
    argv = ["rg", "--files", "--no-config"]
    if include_hidden:
        argv.append("--hidden")
    for ignore in sorted(_DEFAULT_IGNORES):
        argv.extend(["--glob", f"!{ignore}/**", "--glob", f"!{ignore}"])
    if glob_pattern not in {"*", ""}:
        argv.extend(["--glob", glob_pattern])
    argv.extend(_deny_excluded_args())
    argv.extend(["--", str(root)])
    return argv


def run_ripgrep_path_search(
    root: Path, glob_pattern: str, include_hidden: bool, max_matches: int
) -> SearchOutcome:
    """List paths with absolute deadline, deny rules, and safe cleanup."""
    deadline = deadline_from_timeout(_search_deadline_seconds())
    max_files, max_bytes_value = _scanned_limits()
    inv_files, inv_bytes, inventory_reason = _inventory_scan_bounds(root, include_hidden, deadline)
    if inventory_reason is not None:
        return run_python_path_search(root, glob_pattern, include_hidden, max_matches)
    argv = _build_path_argv(root, glob_pattern, include_hidden)
    try:
        proc = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
    except OSError:
        return run_python_path_search(root, glob_pattern, include_hidden, max_matches)
    stderr_thread, stderr_holder = _start_stderr_drain(proc)
    found: list[str] = []
    limit_reason: SearchLimitReason | None = None
    early_exit = False
    try:
        stream = proc.stdout
        if stream is None:
            remaining = (deadline - time.monotonic()) if deadline is not None else None
            try:
                proc.wait(timeout=max(0.0, remaining) if remaining is not None else None)
            except TypeError:
                proc.wait()
            except (subprocess.TimeoutExpired, OSError, ValueError):
                limit_reason = SearchLimitReason.DEADLINE
                early_exit = True
        else:
            iterator = _iter_rg_stream(stream)
            while True:
                if deadline is not None and time.monotonic() >= deadline:
                    limit_reason = SearchLimitReason.DEADLINE
                    early_exit = True
                    break
                remaining = (deadline - time.monotonic()) if deadline is not None else None
                if not _stdout_ready(stream, remaining):
                    try:
                        exited = proc.poll() is not None
                    except (OSError, ValueError, AttributeError):
                        exited = False
                    if exited:
                        break
                    continue
                try:
                    raw_path = next(iterator)
                except StopIteration:
                    break
                raw_path = str(raw_path).rstrip("\r\n")
                if not raw_path:
                    continue
                found.append(display_host_path(Path(raw_path), resolve=False))
                if len(found) > max_matches:
                    limit_reason = SearchLimitReason.RESULT_CAP
                    early_exit = True
                    break
                if len(found) > max_files:
                    limit_reason = SearchLimitReason.SCANNED_FILES
                    early_exit = True
                    break
                if deadline is not None and time.monotonic() >= deadline:
                    limit_reason = SearchLimitReason.DEADLINE
                    early_exit = True
                    break
        if early_exit:
            terminate_process_group(proc)
    finally:
        try:
            stream_obj = getattr(proc, "stdout", None)
            if stream_obj is not None:
                stream_obj.close()
        except (OSError, ValueError, AttributeError):
            pass
        try:
            reap_process(proc)
        except (OSError, ValueError, AttributeError, TypeError):
            pass
    _finish_stderr_drain(stderr_thread, stderr_holder)
    capped = limit_reason == SearchLimitReason.RESULT_CAP
    kept = found[:max_matches] if capped else found[:max_matches]
    total = len(found) if not capped else max_matches + 1
    if not capped and deadline is not None and time.monotonic() >= deadline:
        limit_reason = SearchLimitReason.DEADLINE
    counters = SearchCounters(
        scanned_files=max(len(found), min(inv_files, max_files)),
        scanned_bytes=min(inv_bytes, max_bytes_value),
        candidate_matches=total, returned_matches=len(kept),
    )
    return SearchOutcome(
        ok=True, matches=kept, total_found=total,
        count_complete=limit_reason is None, limit_reason=limit_reason,
        counters=counters, engine=SearchEngine.RIPGREP,
    )


def _path_file_bytes(entry_stat: os.stat_result) -> int:
    """Return bounded byte cost for one path entry."""
    try:
        return min(int(entry_stat.st_size), _max_single_file_bytes())
    except (TypeError, ValueError, AttributeError):
        return 0


def run_python_path_search(
    root: Path, glob_pattern: str, include_hidden: bool, max_matches: int
) -> SearchOutcome:
    """Walk paths without following symlinks and honor deny and deadline."""
    deadline = deadline_from_timeout(_search_deadline_seconds())
    max_files, max_bytes = _scanned_limits()
    roots = host_read_scopes()
    found: list[str] = []
    scanned = 0
    scanned_bytes = 0
    skipped = 0
    limit_reason: SearchLimitReason | None = None
    for current_dir, dirs, files in os.walk(root, followlinks=False):
        if deadline is not None and time.monotonic() >= deadline:
            limit_reason = SearchLimitReason.DEADLINE
            break
        current = Path(current_dir)
        _, dir_skipped = _prune_search_dirs(current, dirs, include_hidden)
        skipped += dir_skipped
        for filename in files:
            if deadline is not None and time.monotonic() >= deadline:
                limit_reason = SearchLimitReason.DEADLINE
                break
            item = current / filename
            if _should_skip_name(item, include_hidden):
                continue
            resolved = _resolve_walk_file(item, root, roots)
            if resolved is None:
                skipped += 1
                continue
            _, entry_stat = resolved
            file_cost = _path_file_bytes(entry_stat)
            if scanned >= max_files:
                limit_reason = SearchLimitReason.SCANNED_FILES
                break
            if scanned_bytes >= max_bytes:
                limit_reason = SearchLimitReason.SCANNED_BYTES
                break
            if scanned_bytes + file_cost > max_bytes:
                limit_reason = SearchLimitReason.SCANNED_BYTES
                break
            scanned += 1
            scanned_bytes = min(max_bytes, scanned_bytes + file_cost)
            if glob_pattern and glob_pattern != "*" and not item.match(glob_pattern):
                continue
            found.append(display_host_path(item, resolve=False))
            if len(found) > max_matches:
                limit_reason = SearchLimitReason.RESULT_CAP
                break
        if limit_reason is not None:
            break
    capped = limit_reason == SearchLimitReason.RESULT_CAP
    kept_paths = found[:max_matches] if capped else found[:max_matches]
    total = (max_matches + 1) if capped else len(kept_paths)
    counters = SearchCounters(
        scanned_files=min(scanned, max_files),
        scanned_bytes=min(scanned_bytes, max_bytes),
        candidate_matches=total, returned_matches=len(kept_paths),
        skipped_special_files=skipped,
    )
    return SearchOutcome(
        ok=True, matches=kept_paths, total_found=total,
        count_complete=limit_reason is None, limit_reason=limit_reason,
        counters=counters, engine=SearchEngine.PYTHON,
    )
