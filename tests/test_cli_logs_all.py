"""Tests for the unified ``bqa logs all`` view (app/cli/logs_view.py)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from app.cli.context import CLIContext
from app.cli.errors import CLIError, EXIT_NOT_FOUND, EXIT_USAGE, NotFoundCLIError
from app.cli.logs_view import handle_logs_all
from app.cli.main import main
from app.cli.output import OutputMode
from app.cli.parser import build_parser


def _ctx(tmp_path, *, mode: OutputMode = OutputMode.HUMAN) -> CLIContext:
    return CLIContext(
        repo_root=tmp_path,
        values={},
        base_url="http://127.0.0.1:18427",
        token="",
        request_timeout=5.0,
        output_mode=mode,
    )


def _args(*extra):
    return build_parser().parse_args(["logs", "all", *extra])


@pytest.fixture
def logs_dir(tmp_path):
    path = tmp_path / "logs"
    path.mkdir()
    return path


def _out(capsys) -> str:
    return capsys.readouterr().out


# --------------------------------------------------------------------------
# Snapshot: merge ordering
# --------------------------------------------------------------------------


def test_merge_orders_timestamped_lines_and_trails_unstamped_source(
    logs_dir, capsys
):
    (logs_dir / "server.log").write_text(
        "2026-08-26 10:00:03,000 - INFO - s3\n"
        "2026-08-26 10:00:01,000 - INFO - s1\n",
        encoding="utf-8",
    )
    (logs_dir / "cloudflared.log").write_text(
        "2026-08-26T10:00:02Z INF t2\n", encoding="utf-8"
    )
    (logs_dir / "launcher.log").write_text("[+] L-a\n[+] L-b\n", encoding="utf-8")

    code = handle_logs_all(_ctx(logs_dir.parent), _args())
    lines = _out(capsys).splitlines()

    assert code == 0
    assert [line.split("] ", 1)[1] for line in lines[:3]] == [
        "2026-08-26 10:00:01,000 - INFO - s1",
        "2026-08-26T10:00:02Z INF t2",
        "2026-08-26 10:00:03,000 - INFO - s3",
    ]
    # The wholly unstamped source trails as one file-order block.
    assert lines[3:] == ["[launcher] [+] L-a", "[launcher] [+] L-b"]


def test_continuation_lines_inherit_preceding_timestamp(logs_dir, capsys):
    (logs_dir / "server.log").write_text(
        "2026-08-26 10:00:01,000 - INFO - parent\n"
        "Traceback (most recent call last):\n"
        "2026-08-26 10:00:05,000 - INFO - later\n",
        encoding="utf-8",
    )
    (logs_dir / "cloudflared.log").write_text(
        "2026-08-26T10:00:03Z INF mid\n", encoding="utf-8"
    )

    code = handle_logs_all(_ctx(logs_dir.parent), _args())
    lines = _out(capsys).splitlines()

    assert code == 0
    assert [line.split("] ", 1)[1] for line in lines] == [
        "2026-08-26 10:00:01,000 - INFO - parent",
        "Traceback (most recent call last):",
        "2026-08-26T10:00:03Z INF mid",
        "2026-08-26 10:00:05,000 - INFO - later",
    ]


# --------------------------------------------------------------------------
# Snapshot: tagging and filtering
# --------------------------------------------------------------------------


def test_lines_are_tagged_per_source(logs_dir, capsys):
    (logs_dir / "server.log").write_text("hello\n", encoding="utf-8")
    (logs_dir / "gateway.log").write_text("AUDIT_EVENT: x\n", encoding="utf-8")
    (logs_dir / "desktop-ui.log").write_text("ui ready\n", encoding="utf-8")

    code = handle_logs_all(_ctx(logs_dir.parent), _args())
    lines = _out(capsys).splitlines()

    assert code == 0
    # Untimed blocks trail in source declaration order: server, then
    # audit, then desktop-ui.
    assert lines == [
        "[server] hello",
        "[audit] AUDIT_EVENT: x",
        "[desktop-ui] ui ready",
    ]


def test_grep_filters_after_tagging_so_tags_match(logs_dir, capsys):
    (logs_dir / "server.log").write_text("plain text\n", encoding="utf-8")
    (logs_dir / "cloudflared.log").write_text("INF connector up\n", encoding="utf-8")

    code = handle_logs_all(_ctx(logs_dir.parent), _args("--grep", "tunnel"))
    out = _out(capsys)

    assert code == 0
    assert out == "[tunnel] INF connector up\n"


def test_grep_still_matches_line_content(logs_dir, capsys):
    (logs_dir / "server.log").write_text(
        "INFO ok\nERROR boom\n", encoding="utf-8"
    )

    code = handle_logs_all(_ctx(logs_dir.parent), _args("--grep", "ERROR"))
    out = _out(capsys)

    assert code == 0
    assert out == "[server] ERROR boom\n"


def test_quiet_prints_raw_merged_lines_without_tags(logs_dir, capsys):
    (logs_dir / "server.log").write_text("s-line\n", encoding="utf-8")
    (logs_dir / "launcher.log").write_text("l-line\n", encoding="utf-8")

    code = handle_logs_all(
        _ctx(logs_dir.parent, mode=OutputMode.QUIET), _args("--grep", "line")
    )
    out = _out(capsys)

    assert code == 0
    assert "[" not in out
    assert sorted(out.splitlines()) == ["l-line", "s-line"]


# --------------------------------------------------------------------------
# Snapshot: per-source tail and missing sources
# --------------------------------------------------------------------------


def test_lines_flag_applies_per_source_before_merging(logs_dir, capsys):
    (logs_dir / "server.log").write_text(
        "s1\ns2\ns3\ns4\n", encoding="utf-8"
    )
    (logs_dir / "gateway.log").write_text("a1\na2\n", encoding="utf-8")

    code = handle_logs_all(_ctx(logs_dir.parent), _args("-n", "2"))
    lines = _out(capsys).splitlines()

    assert code == 0
    # Untimed blocks trail in source declaration order: server before audit.
    assert lines == [
        "[server] s3",
        "[server] s4",
        "[audit] a1",
        "[audit] a2",
    ]


def test_missing_and_empty_sources_are_skipped_silently(logs_dir, capsys):
    (logs_dir / "server.log").write_text("only-one\n", encoding="utf-8")
    (logs_dir / "cloudflared.log").write_text("", encoding="utf-8")

    code = handle_logs_all(_ctx(logs_dir.parent), _args())

    assert code == 0
    assert _out(capsys) == "[server] only-one\n"


def test_all_sources_missing_raises_not_found(logs_dir):
    with pytest.raises(NotFoundCLIError) as excinfo:
        handle_logs_all(_ctx(logs_dir.parent), _args())
    assert excinfo.value.exit_code == EXIT_NOT_FOUND


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root can read files regardless of permissions",
)
def test_unreadable_file_warns_once_but_exit_stays_zero(logs_dir, capsys):
    unreadable = logs_dir / "launcher.log"
    unreadable.write_text("secret-ish\n", encoding="utf-8")
    unreadable.chmod(0o000)
    (logs_dir / "server.log").write_text("readable\n", encoding="utf-8")

    try:
        code = handle_logs_all(_ctx(logs_dir.parent), _args())
    finally:
        unreadable.chmod(0o644)
    captured = capsys.readouterr()

    assert code == 0
    assert "[server] readable" in captured.out
    assert "Could not read" in captured.out


def test_negative_lines_is_a_usage_error(logs_dir):
    with pytest.raises(CLIError) as excinfo:
        handle_logs_all(_ctx(logs_dir.parent), _args("-n", "-1"))
    assert "--lines must be zero or greater." in str(excinfo.value)


# --------------------------------------------------------------------------
# Snapshot: JSON shape and --since window
# --------------------------------------------------------------------------


def test_json_entries_carry_source_optional_ts_and_line(logs_dir, capsys):
    (logs_dir / "server.log").write_text(
        "2026-08-26 10:00:01,000 - INFO - stamped\nbare continuation\n",
        encoding="utf-8",
    )
    (logs_dir / "launcher.log").write_text("unstamped\n", encoding="utf-8")

    code = handle_logs_all(_ctx(logs_dir.parent, mode=OutputMode.JSON), _args())
    payload = json.loads(_out(capsys))

    assert code == 0
    assert payload["ok"] is True
    assert payload["status"] == "success"
    entries = payload["entries"]
    assert [entry["source"] for entry in entries] == [
        "server",
        "server",
        "launcher",
    ]
    stamped = entries[0]
    assert stamped["ts"] == "2026-08-26T10:00:01+00:00"
    assert stamped["line"].endswith("stamped")
    assert "ts" not in entries[1]
    assert entries[2] == {"source": "launcher", "line": "unstamped"}
    assert payload["warnings"] == []


def test_since_window_keeps_recent_blocks_only(logs_dir, capsys):
    now = datetime.now(timezone.utc)
    old = (now - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S,000")
    new = (now - timedelta(seconds=10)).strftime("%Y-%m-%d %H:%M:%S,000")
    (logs_dir / "server.log").write_text(
        f"{old} - INFO - ancient\n{new} - INFO - fresh\nfresh continuation\n",
        encoding="utf-8",
    )
    (logs_dir / "launcher.log").write_text("no stamps here\n", encoding="utf-8")

    code = handle_logs_all(_ctx(logs_dir.parent), _args("--since", "1m"))
    lines = _out(capsys).splitlines()

    assert code == 0
    assert len(lines) == 2
    assert all("ancient" not in line for line in lines)
    assert lines[0].endswith("fresh")
    assert lines[1].endswith("fresh continuation")
    # Wholly unstamped sources contribute nothing under --since.
    assert not any("no stamps" in line for line in lines)


def test_invalid_since_duration_is_rejected(logs_dir):
    with pytest.raises(CLIError) as excinfo:
        handle_logs_all(_ctx(logs_dir.parent), _args("--since", "10x"))
    assert excinfo.value.exit_code == EXIT_USAGE


# --------------------------------------------------------------------------
# Follow mode
# --------------------------------------------------------------------------


def test_follow_streams_appended_lines(logs_dir, capsys):
    server = logs_dir / "server.log"
    server.write_text("2026-08-26 10:00:01,000 - INFO - base\n", encoding="utf-8")

    def hook(tick: int) -> None:
        if tick == 1:
            with server.open("a", encoding="utf-8") as handle:
                handle.write("2026-08-26 10:00:02,000 - INFO - appended\n")

    code = handle_logs_all(
        _ctx(logs_dir.parent),
        _args("-n", "5", "-f"),
        poll_interval=0.001,
        max_polls=3,
        poll_hook=hook,
    )
    out = _out(capsys)

    assert code == 0
    assert out.count("base") == 1
    assert "[server] 2026-08-26 10:00:02,000 - INFO - appended\n" in out


def test_follow_survives_rename_and_replace_mid_stream(logs_dir, capsys):
    server = logs_dir / "server.log"
    rotated = logs_dir / "server.log.1"
    server.write_text("2026-08-26 10:00:01,000 - INFO - old-file\n", encoding="utf-8")

    def hook(tick: int) -> None:
        if tick == 1 and not rotated.exists():
            server.rename(rotated)
            server.write_text(
                "2026-08-26 10:00:05,000 - INFO - replacement\n", encoding="utf-8"
            )

    code = handle_logs_all(
        _ctx(logs_dir.parent),
        _args("-n", "5", "-f"),
        poll_interval=0.001,
        max_polls=4,
        poll_hook=hook,
    )
    out = _out(capsys)

    assert code == 0
    assert "old-file" in out
    assert "[server] 2026-08-26 10:00:05,000 - INFO - replacement\n" in out
    assert out.count("replacement") == 1


def test_follow_never_crashes_when_file_is_deleted(logs_dir, capsys):
    launcher = logs_dir / "launcher.log"
    server = logs_dir / "server.log"
    server.write_text("2026-08-26 10:00:01,000 - INFO - keep\n", encoding="utf-8")
    launcher.write_text("[+] gone soon\n", encoding="utf-8")

    def hook(tick: int) -> None:
        if tick == 1 and launcher.exists():
            launcher.unlink()

    code = handle_logs_all(
        _ctx(logs_dir.parent),
        _args("-f"),
        poll_interval=0.001,
        max_polls=3,
        poll_hook=hook,
    )

    assert code == 0
    assert "keep" in _out(capsys)


def test_follow_picks_up_late_created_source(logs_dir, capsys):
    created = logs_dir / "desktop-ui.log"

    def hook(tick: int) -> None:
        if tick == 1 and not created.exists():
            created.write_text("window shown\n", encoding="utf-8")

    (logs_dir / "server.log").write_text("srv\n", encoding="utf-8")
    code = handle_logs_all(
        _ctx(logs_dir.parent),
        _args("-f"),
        poll_interval=0.001,
        max_polls=3,
        poll_hook=hook,
    )
    out = _out(capsys)

    assert code == 0
    assert "[desktop-ui] window shown\n" in out


def test_follow_interrupt_exits_cleanly_without_traceback(logs_dir, capsys):
    (logs_dir / "server.log").write_text("content\n", encoding="utf-8")

    def hook(_tick: int) -> None:
        raise KeyboardInterrupt

    code = handle_logs_all(
        _ctx(logs_dir.parent),
        _args("-f"),
        poll_interval=0.001,
        max_polls=5,
        poll_hook=hook,
    )
    captured = capsys.readouterr()

    assert code == 0
    assert "Traceback" not in captured.err


def test_follow_with_json_output_is_rejected(logs_dir):
    (logs_dir / "server.log").write_text("x\n", encoding="utf-8")
    args = build_parser().parse_args(["--json", "logs", "all", "-f"])
    ctx = CLIContext(
        repo_root=logs_dir.parent,
        values={},
        base_url="http://127.0.0.1:18427",
        token="",
        request_timeout=5.0,
        output_mode=OutputMode.JSON,
    )

    with pytest.raises(Exception) as excinfo:  # noqa: B017 - CLIError dataclass
        handle_logs_all(ctx, args)
    assert "--json cannot be combined with log follow mode." in str(excinfo.value)


def test_follow_with_everything_missing_starts_with_not_found(logs_dir):
    with pytest.raises(NotFoundCLIError):
        handle_logs_all(
            _ctx(logs_dir.parent),
            _args("-f"),
            poll_interval=0.001,
            max_polls=2,
        )


# --------------------------------------------------------------------------
# Parser + dispatch wiring
# --------------------------------------------------------------------------


def test_parser_accepts_logs_all_with_flags():
    args = build_parser().parse_args(
        ["logs", "all", "-n", "7", "-f", "--since", "10m", "--grep", "boom"]
    )
    assert args.command == "logs"
    assert args.log_action == "all"
    assert args.lines == 7
    assert args.follow is True
    assert args.since == "10m"
    assert args.grep_text == "boom"


def test_main_dispatch_routes_logs_all(tmp_path, monkeypatch, capsys):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "server.log").write_text("wired\n", encoding="utf-8")
    monkeypatch.setattr("app.cli.context.repo_root", lambda: tmp_path)

    code = main(["logs", "all", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["ok"] is True
    assert payload["entries"] == [{"source": "server", "line": "wired"}]


def test_single_log_target_still_uses_legacy_handler(monkeypatch):
    called = {}
    monkeypatch.setattr(
        "app.cli.commands.logs.handle_logs",
        lambda ctx, args: called.update(ran=True) or 0,
    )

    code = main(["logs", "server"])

    assert code == 0
    assert called.get("ran") is True
