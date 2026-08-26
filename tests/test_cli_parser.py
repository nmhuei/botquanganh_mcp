import argparse

import pytest

from app.cli.context import extract_global_options, normalize_base_url
from app.cli.errors import CLIError
from app.cli.parser import build_parser, parse_line_range


def test_global_options_work_after_subcommand():
    args = build_parser().parse_args(
        extract_global_options(["status", "--json", "--public"])
    )
    assert args.command == "status"
    assert args.json is True
    assert args.public is True


def test_parse_line_ranges():
    assert parse_line_range("20") == (20, 20)
    assert parse_line_range("20:50") == (20, 50)
    assert parse_line_range("20:") == (20, None)
    assert parse_line_range(":50") == (None, 50)
    with pytest.raises(argparse.ArgumentTypeError):
        parse_line_range("0")
    with pytest.raises(argparse.ArgumentTypeError):
        parse_line_range("9:2")


def test_normalize_base_url_accepts_connector_and_api_urls():
    assert normalize_base_url("https://example.test/mcp") == "https://example.test"
    assert normalize_base_url("https://example.test/api/v1/") == "https://example.test"
    assert normalize_base_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000"


def test_parser_covers_primary_command_tree():
    parser = build_parser()
    cases = [
        ["server", "restart"],
        ["ui"],
        ["ui", "--detach"],
        ["tui"],
        ["fs", "cat", "README.md", "--lines", "1:5"],
        ["cmd", "run", "printf ok", "--timeout", "5"],
        ["knowledge", "tools", "--versions"],
        ["logs", "follow", "server"],
        ["config", "validate"],
        ["completion", "fish"],
    ]
    for argv in cases:
        assert parser.parse_args(argv).command


def test_color_option_and_output_modes_are_global():
    args = build_parser().parse_args(
        extract_global_options(
            ["health", "--color", "never", "--quiet", "--no-progress"]
        )
    )
    assert args.command == "health"
    assert args.color == "never"
    assert args.quiet is True
    assert args.no_progress is True


def test_json_and_quiet_are_mutually_exclusive():
    with pytest.raises(CLIError):
        build_parser().parse_args(["--json", "--quiet", "health"])


# ---------------------------------------------------------------------------
# Top-level help invariants (GroupedHelpFormatter in app/cli/parser.py).
# Imports are repeated here instead of moving the existing ones above so the
# original tests stay byte-for-byte untouched.
# ---------------------------------------------------------------------------

import inspect
import re
import sys

from app.cli.parser import GroupedHelpFormatter

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_OTHER_BUCKET = "Other"
_SECTION_TITLES = [
    title for title, _names in GroupedHelpFormatter.COMMAND_SECTIONS
] + [_OTHER_BUCKET]


def _subparsers_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    raise AssertionError("parser exposes no subparsers action")


def _row_matches(line: str, name: str) -> bool:
    """True when *line* is the grouped listing row for *name*.

    Rows are rendered at a two-space indent as ``name<pad>  help``;
    continuation lines are indented far deeper, so anchoring on column 2
    keeps them from ever matching.
    """
    return re.match(rf"^ {{2}}{re.escape(name)}(?:\s{{2}}|$)", line) is not None


def test_help_lists_every_command_exactly_once_in_groups(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    parser = build_parser()
    action = _subparsers_action(parser)
    registered = set(action.choices)
    assert {choice.dest for choice in action._choices_actions} == registered

    title_lines = {f"  {title}" for title in _SECTION_TITLES}
    help_text = parser.format_help()
    section_of: dict[str, str] = {}
    rendered_titles: list[str] = []
    current_title = None
    for line in help_text.splitlines():
        if line in title_lines:
            current_title = line.strip()
            rendered_titles.append(current_title)
            continue
        for name in sorted(registered):
            if _row_matches(line, name):
                assert current_title is not None, (
                    f"command {name!r} rendered outside every themed section"
                )
                assert name not in section_of, (
                    f"command {name!r} listed more than once "
                    f"(again under {current_title!r})"
                )
                section_of[name] = current_title
                break

    assert set(section_of) == registered, (
        f"missing from grouped help: {sorted(registered - set(section_of))}"
    )
    declared = {
        name: title
        for title, names in GroupedHelpFormatter.COMMAND_SECTIONS
        for name in names
        if name in registered
    }
    assert section_of == declared
    assert _OTHER_BUCKET not in rendered_titles, (
        "commands fell into the unlisted Other bucket: "
        f"{[n for n, t in section_of.items() if t == _OTHER_BUCKET]}"
    )
    assert "positional arguments" not in help_text


def test_help_metavar_is_compact():
    usage = build_parser().format_usage()
    assert "<command>" in usage
    assert "{start," not in usage
    oversized = [
        group for group in re.findall(r"\{[^{}]*\}", usage) if len(group) > 40
    ]
    assert oversized == []


def test_grouped_help_respects_width_wrapping(monkeypatch):
    monkeypatch.setenv("COLUMNS", "60")
    monkeypatch.setenv("NO_COLOR", "1")
    help_text = build_parser().format_help()
    offenders = []
    for raw_line in help_text.splitlines():
        visible = _ANSI_RE.sub("", raw_line)
        if len(visible) > 60:
            offenders.append(visible)
    assert offenders == [], f"help lines exceed width 60: {offenders!r}"


_ARGPARSE_SUPPORTS_COLOR = (
    "color" in inspect.signature(argparse.ArgumentParser.__init__).parameters
)


def test_no_color_module_level_on_py314(monkeypatch):
    recorded: list[dict] = []
    original_init = argparse.ArgumentParser.__init__

    def spy_init(self, *args, **kwargs):
        recorded.append(dict(kwargs))
        kwargs.pop("color", None)  # tolerate interpreters without the kwarg
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(sys, "version_info", (3, 14, 0, "final", 0))
    if _ARGPARSE_SUPPORTS_COLOR:
        # No spy yet: the kwarg must reach argparse untouched.
        assert getattr(build_parser(), "color") is False

    monkeypatch.setattr(argparse.ArgumentParser, "__init__", spy_init)
    build_parser()
    assert recorded, "no parser was constructed"
    assert all(kwargs.get("color") is False for kwargs in recorded)

    monkeypatch.setattr(sys, "version_info", (3, 13, 0, "final", 0))
    recorded.clear()
    build_parser()
    assert recorded
    # Python 3.14 argparse forwards its own resolved ``color`` into every
    # subparser constructor, so subparser entries may legitimately carry the
    # key; only the root parser's kwargs show what CLIArgumentParser injected.
    assert "color" not in recorded[0]


def test_subcommand_help_screens_unchanged_by_formatter(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    parser = build_parser()
    action = _subparsers_action(parser)
    fs_action = _subparsers_action(action.choices["fs"])
    write_parser = fs_action.choices["write"]
    assert write_parser.formatter_class is argparse.RawDescriptionHelpFormatter

    root_help = parser.format_help()
    write_help = write_parser.format_help()

    assert "Lifecycle" in root_help
    for title in _SECTION_TITLES:
        assert title not in write_help, (
            f"group header {title!r} leaked into bqa fs write help"
        )
    assert "positional arguments" in write_help
    assert "positional arguments" not in root_help
