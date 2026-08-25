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
        extract_global_options(["health", "--color", "never", "--quiet"])
    )
    assert args.command == "health"
    assert args.color == "never"
    assert args.quiet is True


def test_json_and_quiet_are_mutually_exclusive():
    with pytest.raises(CLIError):
        build_parser().parse_args(["--json", "--quiet", "health"])
