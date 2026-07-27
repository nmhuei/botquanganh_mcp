from __future__ import annotations

import argparse
from typing import Optional

from app.cli import VERSION
from app.cli.errors import CLIError, EXIT_USAGE


class CLIArgumentParser(argparse.ArgumentParser):
    """Argument parser that reports usage errors through the CLI error contract."""

    def error(self, message: str) -> None:
        raise CLIError(message, EXIT_USAGE)


def parse_line_range(value: str) -> tuple[Optional[int], Optional[int]]:
    raw = value.strip()
    if not raw:
        raise argparse.ArgumentTypeError("line range must not be empty")
    if ":" not in raw:
        try:
            line = int(raw)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "line range must be N, N:M, N:, or :M"
            ) from exc
        if line < 1:
            raise argparse.ArgumentTypeError("line numbers are 1-indexed")
        return line, line
    left, right = raw.split(":", 1)
    try:
        start = int(left) if left else None
        end = int(right) if right else None
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "line range must be N, N:M, N:, or :M"
        ) from exc
    if start is not None and start < 1:
        raise argparse.ArgumentTypeError("line numbers are 1-indexed")
    if end is not None and end < 1:
        raise argparse.ArgumentTypeError("line numbers are 1-indexed")
    if start is not None and end is not None and end < start:
        raise argparse.ArgumentTypeError("line range end must be >= start")
    return start, end


def _add_global_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--base-url", help="REST base URL; /mcp and /api/v1 suffixes are accepted"
    )
    parser.add_argument(
        "--public", action="store_true", help="Use the current tunnel URL"
    )
    parser.add_argument(
        "--local", action="store_true", help="Use the local bridge URL (default)"
    )
    parser.add_argument("--token", help="Gateway token")
    parser.add_argument("--token-file", help="Read gateway token from a file")
    parser.add_argument(
        "--request-timeout", type=float, default=15.0, help="HTTP timeout in seconds"
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--json", action="store_true", help="Print stable machine-readable JSON"
    )
    output.add_argument(
        "--quiet", action="store_true", help="Print only the primary value without ANSI"
    )
    parser.add_argument(
        "--color",
        choices=["auto", "always", "never"],
        default="auto",
        help="Color policy for human output (default: auto)",
    )
    parser.add_argument(
        "--no-color", action="store_true", help="Alias for --color never"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Show operation metadata"
    )
    parser.add_argument("--version", action="version", version=f"bqa {VERSION}")


def _content_source(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text")
    group.add_argument("--from", dest="source_file")
    group.add_argument("--stdin", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = CLIArgumentParser(
        prog="bqa",
        description="Operate BotQuangAnh Host MCP from a terminal or automation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  bqa status
  bqa health --json
  bqa fs cat README.md --quiet
  bqa server restart
  bqa doctor --local-only

Output modes:
  human   Styled terminal output (default)
  quiet   Primary value only, without ANSI
  JSON    Stable structured output for automation
""",
    )
    _add_global_options(parser)
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser(
        "start", help="Start/adopt the MCP server and tunnel supervisor"
    )
    commands.add_parser("stop", help="Stop supervisor, tunnel, and server")
    restart = commands.add_parser(
        "restart", help="Restart supervisor, tunnel, and server"
    )
    restart.add_argument(
        "--yes", action="store_true", help="Skip the tunnel URL warning"
    )
    commands.add_parser("status", help="Show runtime status")
    commands.add_parser("url", help="Print the current connector URL")
    help_parser = commands.add_parser("help", help="Show help information")
    help_parser.add_argument("topic", nargs="?", help="Subcommand to get help for")

    server = commands.add_parser("server", help="Manage only the local MCP bridge")
    server_commands = server.add_subparsers(dest="server_command", required=True)
    server_commands.add_parser(
        "restart", help="Restart the bridge without restarting the tunnel"
    )
    server_commands.add_parser("status", help="Show bridge status")

    commands.add_parser("health", help="Read REST health")
    capabilities = commands.add_parser("capabilities", help="Read service capabilities")
    capabilities.add_argument("--tools", action="store_true")
    capabilities.add_argument("--limits", action="store_true")
    capabilities.add_argument("--host", action="store_true")

    fs = commands.add_parser("fs", help="Host filesystem operations through REST")
    fs_commands = fs.add_subparsers(dest="fs_command", required=True)
    fs_ls = fs_commands.add_parser("ls", help="List a host directory")
    fs_ls.add_argument("path", nargs="?", default=".")
    fs_ls.add_argument("--max", type=int, default=500, dest="max_entries")

    fs_cat = fs_commands.add_parser("cat", help="Read a UTF-8 host file")
    fs_cat.add_argument("path")
    fs_cat.add_argument("--lines", type=parse_line_range)
    fs_cat.add_argument("--max-bytes", type=int)

    fs_write = fs_commands.add_parser("write", help="Create or overwrite a host file")
    fs_write.add_argument("path")
    _content_source(fs_write)
    fs_write.add_argument("--no-overwrite", action="store_true")
    fs_write.add_argument("--no-create-parents", action="store_true")

    fs_append = fs_commands.add_parser("append", help="Append to a host file")
    fs_append.add_argument("path")
    _content_source(fs_append)

    fs_replace = fs_commands.add_parser(
        "replace", help="Replace exact text in a host file"
    )
    fs_replace.add_argument("path")
    old_group = fs_replace.add_mutually_exclusive_group(required=True)
    old_group.add_argument("--old")
    old_group.add_argument("--old-file")
    new_group = fs_replace.add_mutually_exclusive_group(required=True)
    new_group.add_argument("--new")
    new_group.add_argument("--new-file")
    fs_replace.add_argument("--expected-count", type=int, default=1)

    fs_mkdir = fs_commands.add_parser("mkdir", help="Create a host directory")
    fs_mkdir.add_argument("path")
    fs_mkdir.add_argument("--no-parents", action="store_true")

    fs_search = fs_commands.add_parser("search", help="Search UTF-8 text recursively")
    fs_search.add_argument("query")
    fs_search.add_argument("--path", default=".")
    fs_search.add_argument("--case-sensitive", action="store_true")
    fs_search.add_argument("--max", type=int, default=100, dest="max_results")

    cmd = commands.add_parser("cmd", help="Inspect or execute a host command")
    cmd_commands = cmd.add_subparsers(dest="cmd_command", required=True)
    cmd_check = cmd_commands.add_parser("check", help="Inspect command policy")
    cmd_check.add_argument("shell_command")
    cmd_run = cmd_commands.add_parser("run", help="Execute a command through REST")
    cmd_run.add_argument("shell_command")
    cmd_run.add_argument("--cwd")
    cmd_run.add_argument("--timeout", type=int, default=30)
    cmd_run.add_argument("--check-first", action="store_true")

    knowledge = commands.add_parser("knowledge", help="Read guides and tool inventory")
    knowledge_commands = knowledge.add_subparsers(
        dest="knowledge_command", required=True
    )
    overview = knowledge_commands.add_parser("overview")
    overview.add_argument("--query", default="")
    guide = knowledge_commands.add_parser("guide")
    guide.add_argument("--query", default="")
    tools = knowledge_commands.add_parser("tools")
    tools.add_argument("--query", default="")
    tools.add_argument("--category", default="")
    tools.add_argument("--versions", action="store_true")
    tools.add_argument("--all", action="store_true", dest="include_unavailable")
    tools.add_argument("--uncatalogued", action="store_true")
    tools.add_argument("--refresh", action="store_true")
    search = knowledge_commands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--category", default="")
    search.add_argument("--versions", action="store_true")
    search.add_argument("--all", action="store_true", dest="include_unavailable")
    search.add_argument("--refresh", action="store_true")
    all_parser = knowledge_commands.add_parser("all")
    all_parser.add_argument("--query", default="")
    all_parser.add_argument("--category", default="")
    all_parser.add_argument("--versions", action="store_true")
    all_parser.add_argument("--all", action="store_true", dest="include_unavailable")
    all_parser.add_argument("--uncatalogued", action="store_true")
    all_parser.add_argument("--refresh", action="store_true")

    logs = commands.add_parser("logs", help="Read local runtime logs")
    logs.add_argument(
        "log_action", choices=["server", "tunnel", "launcher", "audit", "follow"]
    )
    logs.add_argument(
        "follow_target", nargs="?", choices=["server", "tunnel", "launcher", "audit"]
    )
    logs.add_argument("-n", "--lines", type=int, default=100)
    logs.add_argument("-f", "--follow", action="store_true")
    logs.add_argument("--all", action="store_true", dest="all_logs")
    logs.add_argument("--since")
    logs.add_argument("--grep", dest="grep_text")

    config = commands.add_parser("config", help="Inspect and validate .env")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    config_commands.add_parser("show")
    config_get = config_commands.add_parser("get")
    config_get.add_argument("key")
    config_commands.add_parser("path")
    config_validate = config_commands.add_parser("validate")
    config_validate.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as validation failures",
    )

    doctor = commands.add_parser(
        "doctor", help="Run non-destructive local/public diagnostics"
    )
    doctor.add_argument(
        "--strict",
        action="store_true",
        help="Return failure when any warning is present",
    )
    doctor.add_argument(
        "--local-only",
        action="store_true",
        help="Skip public tunnel checks",
    )

    completion = commands.add_parser("completion", help="Generate shell completion")
    completion.add_argument("shell", choices=["bash", "zsh", "fish"])

    commands.add_parser("version", help="Print CLI and service version")
    return parser
