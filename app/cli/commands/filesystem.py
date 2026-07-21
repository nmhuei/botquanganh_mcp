from __future__ import annotations

import sys
from pathlib import Path

from app.cli.client import RESTClient
from app.cli.context import CLIContext
from app.cli.errors import CLIError, EXIT_USAGE, NotFoundCLIError
from app.cli.output import emit_json, key_values, message, table


def _content(args) -> str:
    if getattr(args, "text", None) is not None:
        return args.text
    source_file = getattr(args, "source_file", None)
    if source_file:
        path = Path(source_file).expanduser()
        if not path.is_file():
            raise NotFoundCLIError(f"Local source file not found: {path}")
        return path.read_text(encoding="utf-8")
    if getattr(args, "stdin", False):
        return sys.stdin.read()
    raise CLIError("A content source is required.", EXIT_USAGE)


def _file_text(value: str | None, file_value: str | None, label: str) -> str:
    if value is not None:
        return value
    if file_value:
        path = Path(file_value).expanduser()
        if not path.is_file():
            raise NotFoundCLIError(f"Local {label} file not found: {path}")
        return path.read_text(encoding="utf-8")
    raise CLIError(f"Missing {label} text.", EXIT_USAGE)


def handle_filesystem(ctx: CLIContext, args) -> int:
    client = RESTClient(ctx.base_url, ctx.token, ctx.request_timeout)
    command = args.fs_command

    if command == "ls":
        result = client.get(
            "/api/v1/files",
            query={"path": args.path, "max_entries": args.max_entries},
        )
        if ctx.json_output:
            emit_json(result)
        else:
            rows = []
            for item in result.get("items", []):
                item_type = "dir" if item.get("is_directory") else "link" if item.get("is_symlink") else "file"
                rows.append([item_type, item.get("size_bytes", ""), item.get("path", item.get("name", ""))])
            table(["Type", "Bytes", "Path"], rows)
            if result.get("truncated"):
                message("Directory listing was truncated.", kind="warn", no_color=ctx.no_color)
        return 0

    if command == "cat":
        start_line = end_line = None
        if args.lines:
            start_line, end_line = args.lines
        result = client.get(
            "/api/v1/files/content",
            query={
                "path": args.path,
                "start_line": start_line,
                "end_line": end_line,
                "max_bytes": args.max_bytes,
            },
        )
        if ctx.json_output:
            emit_json(result)
        else:
            content = result.get("content", "")
            sys.stdout.write(content)
            if content and not content.endswith("\n"):
                sys.stdout.write("\n")
            if result.get("truncated"):
                message("File output was truncated.", kind="warn", no_color=ctx.no_color)
        return 0

    if command == "write":
        result = client.put(
            "/api/v1/files/content",
            json_body={
                "path": args.path,
                "content": _content(args),
                "overwrite": not args.no_overwrite,
                "create_parents": not args.no_create_parents,
            },
        )
    elif command == "append":
        result = client.post(
            "/api/v1/files/append",
            json_body={"path": args.path, "content": _content(args)},
        )
    elif command == "replace":
        result = client.patch(
            "/api/v1/files/content",
            json_body={
                "path": args.path,
                "old": _file_text(args.old, args.old_file, "old"),
                "new": _file_text(args.new, args.new_file, "new"),
                "expected_count": args.expected_count,
            },
        )
    elif command == "mkdir":
        result = client.post(
            "/api/v1/directories",
            json_body={"path": args.path, "parents": not args.no_parents},
        )
    elif command == "search":
        result = client.get(
            "/api/v1/search",
            query={
                "query": args.query,
                "path": args.path,
                "case_sensitive": str(args.case_sensitive).lower(),
                "max_results": args.max_results,
            },
        )
        if ctx.json_output:
            emit_json(result)
        else:
            rows = [
                [item.get("path", ""), item.get("line_number", ""), item.get("line", "")]
                for item in result.get("results", [])
            ]
            table(["Path", "Line", "Text"], rows)
            if result.get("truncated"):
                message("Search results were truncated.", kind="warn", no_color=ctx.no_color)
        return 0
    else:
        raise CLIError(f"Unsupported fs command: {command}", EXIT_USAGE)

    if ctx.json_output:
        emit_json(result)
    elif not ctx.quiet:
        key_values([(key, value) for key, value in result.items() if key != "ok"])
    return 0 if result.get("ok", True) else 1
