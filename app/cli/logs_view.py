"""Unified view over every runtime log stream under ``logs/``.

``bqa logs all`` merges the recent tail of each known source into one
interleaved stream so debugging no longer requires hunting for which file
holds which component's output.

Sources and tags
    server      -> logs/server.log       -> ``[server]``
    tunnel      -> logs/cloudflared.log  -> ``[tunnel]``
    launcher    -> logs/launcher.log     -> ``[launcher]``
    audit       -> logs/gateway.log      -> ``[audit]``
    desktop-ui  -> logs/desktop-ui.log   -> ``[desktop-ui]``

Ordering rules
    - Lines whose prefix parses as a timestamp (same ISO-ish rule as the
      single-source reader) interleave by timestamp. Ties break by source
      declaration order, then original file order.
    - A line without its own timestamp inherits the timestamp of the closest
      preceding line from the same file, so multi-line stack traces stay
      attached to their parent. Leading lines with no anchor sort first.
    - A source with no parseable timestamps at all is appended after all
      timestamped entries as one trailing block per source (declaration
      order, file order preserved). "Newest-file-block last" is the accepted
      fallback for formats that cannot be timestamp-ordered.
    - ``--since`` keeps the existing block-based semantics of the single
      source reader: only blocks opened by a timestamped line at or after
      the cutoff survive, so wholly unstamped sources contribute nothing
      under ``--since``.

Flag semantics
    ``-n`` applies PER SOURCE before merging, ``--grep`` filters AFTER the
    ``[source]`` tags are applied (so TEXT may match a tag), ``--json``
    emits objects of the shape ``{source, ts?, line}``, and ``--quiet``
    prints the raw merged lines without tags.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.cli.commands.logs import _duration, _timestamp
from app.cli.context import CLIContext
from app.cli.errors import CLIError, EXIT_USAGE, NotFoundCLIError
from app.cli.output import emit_json, external_text, renderer_for


ALL_LOG_FILES = {
    "server": "server.log",
    "tunnel": "cloudflared.log",
    "launcher": "launcher.log",
    "audit": "gateway.log",
    "desktop-ui": "desktop-ui.log",
}
DEFAULT_POLL_INTERVAL = 0.5

_EPOCH_MIN = datetime.min.replace(tzinfo=timezone.utc)

# Sort buckets: timestamped sources interleave by time (bucket 0); sources
# without any parseable timestamp trail behind as file-order blocks (bucket 1).
_BUCKET_TIMED = 0
_BUCKET_UNTIMED = 1


@dataclass(slots=True)
class _Row:
    """One merged log line plus everything needed to sort and render it."""

    order: int
    index: int
    tag: str
    line: str
    own_ts: datetime | None
    sort_ts: datetime
    bucket: int

    def sort_key(self) -> tuple[int, datetime, int, int]:
        return (self.bucket, self.sort_ts, self.order, self.index)


@dataclass(slots=True)
class _FollowState:
    """Per-source bookkeeping for the follow poll loop."""

    tag: str
    order: int
    path: Path
    inode: int | None = None
    position: int = 0
    partial: bytes = b""
    warned: bool = False


def _logs_dir(ctx: CLIContext) -> Path:
    return Path(ctx.repo_root) / "logs"


def _tail_lines(
    path: Path,
    *,
    lines: int,
    cutoff: datetime | None,
) -> list[str]:
    """Return the last ``lines`` lines of ``path`` after the since filter.

    The caller has already validated ``lines >= 0``. Missing files raise
    ``FileNotFoundError``; other read failures raise ``OSError``.
    """
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if cutoff is not None:
        kept: list[str] = []
        include_block = False
        for line in content:
            stamp = _timestamp(line)
            if stamp is not None:
                include_block = stamp >= cutoff
            if include_block:
                kept.append(line)
        content = kept
    return content[-lines:] if lines else []


def _source_rows(
    tag: str,
    order: int,
    selected: list[str],
) -> list[_Row]:
    """Build sortable rows for one source, forward-filling timestamps."""
    timed = any(_timestamp(line) is not None for line in selected)
    rows: list[_Row] = []
    last_seen: datetime | None = None
    for index, line in enumerate(selected):
        own_ts = _timestamp(line)
        if own_ts is not None:
            last_seen = own_ts
        if timed:
            rows.append(
                _Row(
                    order=order,
                    index=index,
                    tag=tag,
                    line=line,
                    own_ts=own_ts,
                    sort_ts=own_ts or last_seen or _EPOCH_MIN,
                    bucket=_BUCKET_TIMED,
                )
            )
        else:
            rows.append(
                _Row(
                    order=order,
                    index=index,
                    tag=tag,
                    line=line,
                    own_ts=None,
                    sort_ts=_EPOCH_MIN,
                    bucket=_BUCKET_UNTIMED,
                )
            )
    return rows


def _collect_snapshot(
    ctx: CLIContext,
    *,
    lines: int,
    cutoff: datetime | None,
) -> tuple[list[_Row], list[str], bool]:
    """Gather the merged snapshot rows.

    Returns ``(rows, warnings, found_any)`` where ``found_any`` reports
    whether at least one source file existed on disk.
    """
    warnings: list[str] = []
    rows: list[_Row] = []
    found_any = False
    for order, (tag, filename) in enumerate(ALL_LOG_FILES.items()):
        path = _logs_dir(ctx) / filename
        try:
            selected = _tail_lines(path, lines=lines, cutoff=cutoff)
        except FileNotFoundError:
            continue
        except OSError:
            warnings.append(f"Could not read log file: {path}")
            continue
        found_any = True
        rows.extend(_source_rows(tag, order, selected))
    rows.sort(key=_Row.sort_key)
    return rows, warnings, found_any


def _keep(row_tag: str, row_line: str, grep_text: str | None) -> bool:
    """Apply grep AFTER tagging so TEXT can match the ``[source]`` tag too."""
    return grep_text is None or grep_text in f"[{row_tag}] {row_line}"


def _visible_rows(rows: list[_Row], grep_text: str | None) -> list[_Row]:
    return [row for row in rows if _keep(row.tag, row.line, grep_text)]


def _print_row(row: _Row, *, tagged: bool, color_mode: str) -> None:
    text = external_text(row.line, color_mode=color_mode)
    print(f"[{row.tag}] {text}" if tagged else text)


def _render_snapshot(ctx: CLIContext, rows: list[_Row], warnings: list[str]) -> None:
    if ctx.json_output:
        entries = []
        for row in rows:
            entry: dict[str, str] = {"source": row.tag, "line": row.line}
            if row.own_ts is not None:
                entry["ts"] = row.own_ts.astimezone(timezone.utc).isoformat()
            entries.append(entry)
        emit_json(
            {
                "ok": True,
                "status": "success",
                "entries": entries,
                "warnings": warnings,
            }
        )
        return
    if ctx.quiet:
        # Quiet mode prints raw data only; warnings go to stderr.
        for warning in warnings:
            print(warning, file=sys.stderr)
        for row in rows:
            _print_row(row, tagged=False, color_mode=ctx.color)
        return
    renderer = renderer_for(ctx)
    for warning in warnings:
        renderer.warning(warning)
    for row in rows:
        _print_row(row, tagged=True, color_mode=ctx.color)


def _poll_once(states: list[_FollowState], warnings: list[str]) -> list[_Row]:
    """Read newly appended bytes from every followed source.

    Handles rotation (inode change) and truncation (size shrink) by reading
    the replacement file from its start, and silently skips sources that do
    not currently exist so they resume automatically when recreated.
    """
    fresh: list[_Row] = []
    for state in states:
        try:
            stat = state.path.stat()
        except FileNotFoundError:
            state.inode = None
            state.position = 0
            state.partial = b""
            continue
        except OSError:
            if not state.warned:
                warnings.append(f"Could not read log file: {state.path}")
                state.warned = True
            continue
        rotated = (
            state.inode is not None and stat.st_ino != state.inode
        ) or stat.st_size < state.position
        reappeared = state.inode is None and stat.st_size > 0
        if rotated or reappeared:
            state.inode = stat.st_ino
            state.position = 0
            state.partial = b""
        elif state.inode is None:
            state.inode = stat.st_ino
        if stat.st_size == state.position:
            continue
        try:
            with state.path.open("rb") as handle:
                handle.seek(state.position)
                chunk = handle.read()
        except OSError:
            if not state.warned:
                warnings.append(f"Could not read log file: {state.path}")
                state.warned = True
            continue
        state.warned = False
        state.position += len(chunk)
        data = state.partial + chunk
        *complete, state.partial = data.split(b"\n")
        if not complete:
            continue
        decoded = [raw.decode("utf-8", errors="replace") for raw in complete]
        fresh.extend(_source_rows(state.tag, state.order, decoded))
    return fresh


def _follow_all(
    ctx: CLIContext,
    args,
    *,
    cutoff: datetime | None,
    poll_interval: float,
    max_polls: int | None,
    poll_hook: Callable[[int], None] | None,
) -> int:
    states = [
        _FollowState(tag=tag, order=order, path=_logs_dir(ctx) / filename)
        for order, (tag, filename) in enumerate(ALL_LOG_FILES.items())
    ]
    if all(not state.path.is_file() for state in states):
        raise NotFoundCLIError(f"No runtime log files found in {_logs_dir(ctx)}")

    rows, warnings, _found = _collect_snapshot(ctx, lines=args.lines, cutoff=cutoff)
    _render_snapshot(ctx, rows, warnings)
    for state in states:
        try:
            stat = state.path.stat()
        except OSError:
            continue
        state.inode = stat.st_ino
        state.position = stat.st_size

    ticks_done = 0
    try:
        while max_polls is None or ticks_done < max_polls:
            if poll_hook is not None:
                poll_hook(ticks_done)
            batch_warnings: list[str] = []
            fresh = _poll_once(states, batch_warnings)
            # Lines arriving in the same poll tick interleave by timestamp,
            # same as the snapshot; cross-tick ordering follows arrival.
            fresh.sort(key=_Row.sort_key)
            visible = _visible_rows(fresh, args.grep_text)
            if visible or batch_warnings:
                _render_snapshot(ctx, visible, batch_warnings)
                sys.stdout.flush()
            ticks_done += 1
            if max_polls is None or ticks_done < max_polls:
                time.sleep(poll_interval)
    except KeyboardInterrupt:
        # Clean SIGINT shutdown: no traceback, success exit code.
        return 0
    return 0


def handle_logs_all(
    ctx: CLIContext,
    args,
    *,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    max_polls: int | None = None,
    poll_hook: Callable[[int], None] | None = None,
) -> int:
    """Handle ``bqa logs all``: one interleaved view over every log source."""
    if getattr(args, "since", None):
        cutoff = datetime.now(timezone.utc) - _duration(args.since)
    else:
        cutoff = None
    if getattr(args, "lines", 0) < 0:
        raise CLIError("--lines must be zero or greater.", EXIT_USAGE)
    follow = bool(getattr(args, "follow", False))
    if follow:
        if ctx.json_output:
            raise CLIError(
                "--json cannot be combined with log follow mode.", EXIT_USAGE
            )
        return _follow_all(
            ctx,
            args,
            cutoff=cutoff,
            poll_interval=poll_interval,
            max_polls=max_polls,
            poll_hook=poll_hook,
        )
    rows, warnings, found_any = _collect_snapshot(ctx, lines=args.lines, cutoff=cutoff)
    if not found_any:
        raise NotFoundCLIError(f"No runtime log files found in {_logs_dir(ctx)}")
    _render_snapshot(ctx, _visible_rows(rows, args.grep_text), warnings)
    return 0
