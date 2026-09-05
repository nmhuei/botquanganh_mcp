from __future__ import annotations

import argparse
import sys

from app.cli import VERSION
from app.cli.errors import EXIT_USAGE, CLIError
from app.cli.output import style, wrap_visible


class CLIArgumentParser(argparse.ArgumentParser):
    """Argument parser that reports usage errors through the CLI error contract."""

    def __init__(self, *args, **kwargs):
        if sys.version_info >= (3, 14):
            # Python 3.14 colorizes help with its own blue/green/yellow
            # palette; this CLI owns all styling through app.cli.output, so
            # argparse's injected colors are disabled unconditionally.
            kwargs["color"] = False
        super().__init__(*args, **kwargs)

    def error(self, message: str) -> None:
        raise CLIError(message, EXIT_USAGE)


class GroupedHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Top-level help formatter that lists subcommands in themed sections.

    Section titles are styled through the shared ``style()`` helper so they
    honor NO_COLOR, TERM=dumb, CI, and non-TTY suppression like every other
    human-facing screen. Any subcommand missing from COMMAND_SECTIONS still
    appears under an "Other" fallback bucket, so grouping can never drop a
    registered command.
    """

    COMMAND_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("Lifecycle", ("start", "stop", "restart", "server", "url")),
        ("Interface", ("ui", "tui")),
        ("Inspection", ("status", "health", "capabilities", "knowledge", "logs", "chats")),
        ("Files & commands", ("fs", "cmd")),
        ("Diagnostics", ("doctor",)),
        ("Config & help", ("config", "completion", "version", "help")),
    )

    def start_section(self, heading: str) -> None:
        if heading == "positional arguments":
            # Section titles below replace the stock flat listing header.
            heading = argparse.SUPPRESS
        super().start_section(heading)

    def _format_action(self, action: argparse.Action) -> str:
        if isinstance(action, argparse._SubParsersAction):
            grouped = self._format_grouped_commands(action)
            if grouped is not None:
                return grouped
        return super()._format_action(action)

    def _format_grouped_commands(
        self, action: argparse._SubParsersAction
    ) -> str | None:
        helps = {
            choice.dest: choice.help or ""
            for choice in getattr(action, "_choices_actions", [])
        }
        blocks: list[tuple[str, list[tuple[str, str]]]] = []
        listed: set[str] = set()
        for title, names in self.COMMAND_SECTIONS:
            rows = [
                (name, helps.get(name, ""))
                for name in names
                if name in action.choices
            ]
            listed.update(name for name, _ in rows)
            if rows:
                blocks.append((title, rows))
        leftovers = [name for name in action.choices if name not in listed]
        if leftovers:
            blocks.append(
                ("Other", [(name, helps.get(name, "")) for name in leftovers])
            )
        if not blocks:
            return None

        indent = " " * self._current_indent
        name_width = max(len(name) for _, rows in blocks for name, _ in rows)
        label_width = self._current_indent + name_width + 2
        wrap_width = max(20, self._width - label_width)

        parts: list[str] = []
        for index, (title, rows) in enumerate(blocks):
            if index:
                parts.append("\n")
            parts.append(f"{indent}{style(title, 'dim')}\n")
            for name, text in rows:
                lines = wrap_visible(text, wrap_width) if text else [""]
                parts.append(
                    f"{indent}{name:<{name_width}}  {lines[0]}".rstrip() + "\n"
                )
                for continuation in lines[1:]:
                    parts.append(f"{' ' * label_width}{continuation}".rstrip() + "\n")
        return "".join(parts)


def parse_line_range(value: str) -> tuple[int | None, int | None]:
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
        "--no-progress",
        action="store_true",
        help="Hide live progress bars and spinners",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Show operation metadata"
    )
    parser.add_argument("--version", action="version", version=f"bqa {VERSION}")


def _content_source(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text", help="Content to write literally")
    group.add_argument("--from", dest="source_file", help="Read content from a local file")
    group.add_argument(
        "--stdin", action="store_true", help="Read content from standard input"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = CLIArgumentParser(
        prog="bqa",
        description="Operate BotQuangAnh Host MCP from a terminal or automation.",
        formatter_class=GroupedHelpFormatter,
        epilog="""Examples:
  bqa status
  bqa health --json
  bqa fs cat README.md --quiet
  bqa logs audit --since 10m
  bqa server restart
  bqa doctor --local-only

Output modes:
  human   Styled terminal output (default)
  quiet   Primary value only, without ANSI
  JSON    Stable structured output for automation
""",
    )
    _add_global_options(parser)
    commands = parser.add_subparsers(
        dest="command", required=True, metavar="<command>"
    )

    commands.add_parser(
        "start", help="Start/adopt the MCP server and tunnel supervisor"
    )
    commands.add_parser("stop", help="Stop supervisor, tunnel, and server")
    restart = commands.add_parser(
        "restart", help="Restart only the MCP server; preserve tunnel PID and URL"
    )
    restart.add_argument(
        "--yes", action="store_true", help=argparse.SUPPRESS
    )
    commands.add_parser("status", help="Show runtime status")
    commands.add_parser("url", help="Print the current connector URL")
    ui = commands.add_parser("ui", help="Open the native Python desktop control center")
    ui.add_argument(
        "--foreground",
        action="store_true",
        help="Compatibility alias: open the UI detached in the background",
    )
    ui.add_argument(
        "--detach",
        action="store_true",
        help="Open the UI detached in the background (the default)",
    )
    ui.add_argument(
        "--inline",
        action="store_true",
        help="Run attached to this terminal until the UI window is closed",
    )
    commands.add_parser("tui", help="Open the terminal control center")
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
    capabilities.add_argument(
        "--tools", action="store_true", help="Show only the MCP tool list"
    )
    capabilities.add_argument(
        "--limits", action="store_true", help="Show only resource limits"
    )
    capabilities.add_argument(
        "--host", action="store_true", help="Show only host runtime facts"
    )

    fs = commands.add_parser("fs", help="Host filesystem operations through REST")
    fs_commands = fs.add_subparsers(dest="fs_command", required=True)
    fs_ls = fs_commands.add_parser("ls", help="List a host directory")
    fs_ls.add_argument(
        "path", nargs="?", default=".", help="Directory to list (default: workspace root)"
    )
    fs_ls.add_argument(
        "--max",
        type=int,
        default=500,
        dest="max_entries",
        help="Maximum entries to return (default: 500)",
    )

    fs_cat = fs_commands.add_parser("cat", help="Read a UTF-8 host file")
    fs_cat.add_argument("path", help="Host file to read")
    fs_cat.add_argument(
        "--lines", type=parse_line_range, help="Line range: N, N:M, N:, or :M"
    )
    fs_cat.add_argument(
        "--max-bytes", type=int, help="Maximum bytes to return"
    )

    fs_write = fs_commands.add_parser(
        "write",
        help="Create or overwrite a host file",
        epilog="""Examples:
  bqa fs write notes/todo.txt --text "hello"
  cat local.txt | bqa fs write notes/todo.txt --stdin""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    fs_write.add_argument("path", help="Host file to create or overwrite")
    _content_source(fs_write)
    fs_write.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Fail instead of overwriting an existing file",
    )
    fs_write.add_argument(
        "--no-create-parents",
        action="store_true",
        help="Do not create missing parent directories",
    )

    fs_append = fs_commands.add_parser("append", help="Append to a host file")
    fs_append.add_argument("path", help="Host file to append to")
    _content_source(fs_append)

    fs_replace = fs_commands.add_parser(
        "replace",
        help="Replace exact text in a host file",
        epilog="""Example:
  bqa fs replace app.py --old "TODO" --new "DONE" --expected-count 1""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    fs_replace.add_argument("path", help="Host file to update")
    old_group = fs_replace.add_mutually_exclusive_group(required=True)
    old_group.add_argument("--old", help="Exact text to find")
    old_group.add_argument(
        "--old-file", help="Read the text to find from a local file"
    )
    new_group = fs_replace.add_mutually_exclusive_group(required=True)
    new_group.add_argument("--new", help="Replacement text")
    new_group.add_argument(
        "--new-file", help="Read the replacement text from a local file"
    )
    fs_replace.add_argument(
        "--expected-count",
        type=int,
        default=1,
        help="Expected number of matches (default: 1)",
    )

    fs_mkdir = fs_commands.add_parser("mkdir", help="Create a host directory")
    fs_mkdir.add_argument("path", help="Directory to create")
    fs_mkdir.add_argument(
        "--no-parents",
        action="store_true",
        help="Do not create missing parent directories",
    )

    fs_search = fs_commands.add_parser(
        "search", help="Search UTF-8 text recursively"
    )
    fs_search.add_argument("query", help="Text to search for")
    fs_search.add_argument(
        "--path", default=".", help="Directory to search (default: workspace root)"
    )
    fs_search.add_argument(
        "--case-sensitive", action="store_true", help="Match letter case exactly"
    )
    fs_search.add_argument(
        "--max",
        type=int,
        default=100,
        dest="max_results",
        help="Maximum results (default: 100)",
    )

    cmd = commands.add_parser("cmd", help="Inspect or execute a host command")
    cmd_commands = cmd.add_subparsers(dest="cmd_command", required=True)
    cmd_check = cmd_commands.add_parser(
        "check",
        help="Inspect command policy",
        epilog="""Example:
  bqa cmd check "ls -la" """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    cmd_check.add_argument(
        "shell_command", help="Command line to inspect against policy"
    )
    cmd_run = cmd_commands.add_parser(
        "run",
        help="Execute a command through REST",
        epilog="""Examples:
  bqa cmd run "df -h"
  bqa cmd run "./scripts/run.sh" --timeout 60 --check-first""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    cmd_run.add_argument("shell_command", help="Command line to execute on the host")
    cmd_run.add_argument("--cwd", help="Working directory for the command")
    cmd_run.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Seconds before the command is stopped (default: 30)",
    )
    cmd_run.add_argument(
        "--check-first",
        action="store_true",
        help="Check policy first and skip execution when blocked",
    )

    knowledge = commands.add_parser(
        "knowledge", help="Read guides and tool inventory"
    )
    knowledge_commands = knowledge.add_subparsers(
        dest="knowledge_command", required=True
    )
    overview = knowledge_commands.add_parser(
        "overview", help="Show workspace profile and knowledge sources"
    )
    overview.add_argument("--query", default="", help="Filter guides by text")
    guide = knowledge_commands.add_parser("guide", help="Read stored operational guides")
    guide.add_argument("--query", default="", help="Filter guides by text")
    tools = knowledge_commands.add_parser(
        "tools", help="List catalogued host tools"
    )
    tools.add_argument("--query", default="", help="Filter tools by name or purpose")
    tools.add_argument("--category", default="", help="Filter by category name")
    tools.add_argument(
        "--versions", action="store_true", help="Include tool versions"
    )
    tools.add_argument(
        "--all",
        action="store_true",
        dest="include_unavailable",
        help="Include unavailable tools",
    )
    tools.add_argument(
        "--uncatalogued",
        action="store_true",
        help="List PATH commands missing from the catalog",
    )
    tools.add_argument(
        "--refresh", action="store_true", help="Rebuild the catalog before responding"
    )
    search = knowledge_commands.add_parser(
        "search", help="Search guides and the tool catalog together"
    )
    search.add_argument("query", help="Text to search for")
    search.add_argument("--category", default="", help="Filter tools by category")
    search.add_argument(
        "--versions", action="store_true", help="Include tool versions"
    )
    search.add_argument(
        "--all",
        action="store_true",
        dest="include_unavailable",
        help="Include unavailable tools",
    )
    search.add_argument(
        "--refresh", action="store_true", help="Rebuild the catalog before responding"
    )
    all_parser = knowledge_commands.add_parser(
        "all", help="Show overview, guides, and tool inventory"
    )
    all_parser.add_argument("--query", default="", help="Filter guides by text")
    all_parser.add_argument("--category", default="", help="Filter tools by category")
    all_parser.add_argument(
        "--versions", action="store_true", help="Include tool versions"
    )
    all_parser.add_argument(
        "--all",
        action="store_true",
        dest="include_unavailable",
        help="Include unavailable tools",
    )
    all_parser.add_argument(
        "--uncatalogued",
        action="store_true",
        help="List PATH commands missing from the catalog",
    )
    all_parser.add_argument(
        "--refresh", action="store_true", help="Rebuild the catalog before responding"
    )

    logs = commands.add_parser(
        "logs",
        help="Read local runtime logs",
        epilog="""Examples:
  bqa logs server -n 50
  bqa logs audit --since 10m --grep error
  bqa logs all -n 50
  bqa logs all -f
  bqa logs follow --all""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    logs.add_argument(
        "log_action",
        choices=["server", "tunnel", "launcher", "audit", "follow", "all"],
        help="Log to read, 'all' to merge every stream, or 'follow' to stream live",
    )
    logs.add_argument(
        "follow_target",
        nargs="?",
        choices=["server", "tunnel", "launcher", "audit"],
        help="Stream to follow when the action is 'follow'",
    )
    logs.add_argument(
        "-n",
        "--lines",
        type=int,
        default=100,
        help="Lines shown PER SOURCE before merging (default: 100)",
    )
    logs.add_argument(
        "-f",
        "--follow",
        action="store_true",
        help="Keep streaming new lines until interrupted (with 'all': every source)",
    )
    logs.add_argument(
        "--all", action="store_true", dest="all_logs", help="Read every log stream"
    )
    logs.add_argument(
        "--since",
        help="Only entries newer than DURATION (e.g. 30s, 10m, 2h, 1d)",
    )
    logs.add_argument(
        "--grep", dest="grep_text", help="Only lines containing TEXT"
    )

    chats = commands.add_parser(
        "chats",
        help="Inspect local chat workspaces",
        epilog="""Examples:
  bqa chats
  bqa chats show <chat-id> --json""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    chats_commands = chats.add_subparsers(dest="chats_command")
    chats_commands.add_parser("list", help="List workspaces by recent activity")
    chats_show = chats_commands.add_parser(
        "show",
        help="Show one workspace's path, state notes, and journal counts",
    )
    chats_show.add_argument("chat_id", help="Chat identifier to inspect")
    chats_logs = chats_commands.add_parser(
        "logs", help="Display classified workspace journal events"
    )
    chats_logs.add_argument("chat_id", help="Chat identifier to inspect")
    severity_filters = chats_logs.add_mutually_exclusive_group()
    severity_filters.add_argument(
        "--severity",
        choices=("debug", "info", "warn", "error"),
        help="Filter by one normalized severity",
    )
    severity_filters.add_argument(
        "--min-severity",
        choices=("debug", "info", "warn", "error"),
        help="Keep this severity and anything more severe",
    )
    chats_logs.add_argument(
        "--category",
        choices=("api", "configuration", "file", "host", "process", "session"),
        help="Filter by normalized event category",
    )
    chats_logs.add_argument(
        "--outcome",
        choices=("success", "failure", "unknown"),
        help="Filter by normalized operation outcome",
    )
    chats_logs.add_argument(
        "--action",
        help="Filter by exact host tool/action name",
    )
    chats_logs.add_argument(
        "--phase",
        choices=("started", "result"),
        help="Filter operation start/result records",
    )
    chats_logs.add_argument(
        "--limit", type=int, default=50, help="Newest events to display (1-1000)"
    )
    chats_archive = chats_commands.add_parser("archive", help="Archive one active workspace")
    chats_archive.add_argument("chat_id", help="Chat identifier to archive")
    chats_restore = chats_commands.add_parser("restore", help="Restore one archived workspace")
    chats_restore.add_argument("chat_id", help="Chat identifier to restore")
    chats_delete = chats_commands.add_parser("delete", help="Permanently delete one archived workspace")
    chats_delete.add_argument("chat_id", help="Archived chat identifier to delete")
    chats_delete.add_argument("--yes", action="store_true", help="Confirm permanent deletion")
    chats_prune = chats_commands.add_parser("prune", help="Plan or apply lifecycle sweep actions")
    chats_prune.add_argument("--apply", action="store_true", help="Apply planned archive/delete actions")
    chats_commands.add_parser("stats", help="Show workspace counts and storage usage")

    config = commands.add_parser("config", help="Inspect and validate .env")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    config_commands.add_parser("show", help="Print effective .env values")
    config_get = config_commands.add_parser("get", help="Print one .env value")
    config_get.add_argument("key", help="Configuration key to print")
    config_commands.add_parser("path", help="Print the .env file location")
    config_validate = config_commands.add_parser(
        "validate", help="Run non-destructive configuration checks"
    )
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
    completion.add_argument(
        "shell", choices=["bash", "zsh", "fish"], help="Shell to generate for"
    )

    commands.add_parser("version", help="Print CLI and service version")
    return parser
