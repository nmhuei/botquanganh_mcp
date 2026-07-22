from __future__ import annotations

import sys
from pathlib import Path

from app.cli.client import RESTClient
from app.cli.context import CLIContext
from app.cli.errors import CLIError, EXIT_USAGE, NotFoundCLIError
from app.cli.output import emit_json, emit_quiet, renderer_for


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


def _item_type(item: dict) -> str:
    if item.get("is_directory"):
        return "directory"
    if item.get("is_symlink"):
        return "symlink"
    return "file"


def _render_mutation(ctx: CLIContext, result: dict, command: str) -> int:
    ok = bool(result.get("ok", True))
    state = "success" if ok else "failed"
    payload = {**result, "status": state, "operation": f"fs_{command}"}
    if ctx.json_output:
        emit_json(payload)
    elif ctx.quiet:
        primary = result.get("path") or state
        emit_quiet(primary)
    else:
        renderer = renderer_for(ctx)
        renderer.header("Filesystem", command.capitalize())
        renderer.blank()
        renderer.status(
            state,
            f"{command.capitalize()} completed"
            if ok
            else f"{command.capitalize()} failed",
        )
        details = [
            (key.replace("_", " ").title(), value)
            for key, value in result.items()
            if key != "ok"
        ]
        if details:
            renderer.blank()
            renderer.facts(details)
    return 0 if ok else 1


def handle_filesystem(ctx: CLIContext, args) -> int:
    client = RESTClient(ctx.base_url, ctx.token, ctx.request_timeout)
    command = args.fs_command

    if command == "ls":
        result = client.get(
            "/api/v1/files",
            query={"path": args.path, "max_entries": args.max_entries},
        )
        items = result.get("items", [])
        if ctx.json_output:
            emit_json({**result, "status": "success"})
        elif ctx.quiet:
            emit_quiet([item.get("path", item.get("name", "")) for item in items])
        else:
            renderer = renderer_for(ctx)
            renderer.header("Filesystem listing", str(result.get("path", args.path)))
            renderer.blank()
            renderer.status("success", f"{len(items)} entries")
            if items:
                renderer.blank()
                renderer.table(
                    ["TYPE", "BYTES", "PATH"],
                    [
                        [
                            _item_type(item),
                            item.get("size_bytes", ""),
                            item.get("path", item.get("name", "")),
                        ]
                        for item in items
                    ],
                    numeric_columns=[1],
                )
            if result.get("truncated"):
                renderer.blank()
                renderer.warning("Directory listing was truncated.")
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
            emit_json({**result, "status": "success"})
        else:
            content = str(result.get("content", ""))
            sys.stdout.write(content)
            if content and not content.endswith("\n"):
                sys.stdout.write("\n")
            if result.get("truncated") and not ctx.quiet:
                renderer_for(ctx, stream=sys.stderr).warning(
                    "File output was truncated."
                )
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
        return _render_mutation(ctx, result, command)
    if command == "append":
        result = client.post(
            "/api/v1/files/append",
            json_body={"path": args.path, "content": _content(args)},
        )
        return _render_mutation(ctx, result, command)
    if command == "replace":
        result = client.patch(
            "/api/v1/files/content",
            json_body={
                "path": args.path,
                "old": _file_text(args.old, args.old_file, "old"),
                "new": _file_text(args.new, args.new_file, "new"),
                "expected_count": args.expected_count,
            },
        )
        return _render_mutation(ctx, result, command)
    if command == "mkdir":
        result = client.post(
            "/api/v1/directories",
            json_body={"path": args.path, "parents": not args.no_parents},
        )
        return _render_mutation(ctx, result, command)
    if command == "search":
        result = client.get(
            "/api/v1/search",
            query={
                "query": args.query,
                "path": args.path,
                "case_sensitive": str(args.case_sensitive).lower(),
                "max_results": args.max_results,
            },
        )
        matches = result.get("results", [])
        if ctx.json_output:
            emit_json({**result, "status": "success"})
        elif ctx.quiet:
            emit_quiet(
                [
                    f"{item.get('path', '')}:{item.get('line_number', '')}:{item.get('line', '')}"
                    for item in matches
                ]
            )
        else:
            renderer = renderer_for(ctx)
            renderer.header("Filesystem search", args.query)
            renderer.blank()
            renderer.status("success", f"{len(matches)} matches")
            if matches:
                renderer.blank()
                renderer.table(
                    ["PATH", "LINE", "TEXT"],
                    [
                        [
                            item.get("path", ""),
                            item.get("line_number", ""),
                            item.get("line", ""),
                        ]
                        for item in matches
                    ],
                    numeric_columns=[1],
                )
            if result.get("truncated"):
                renderer.blank()
                renderer.warning("Search results were truncated.")
        return 0

    raise CLIError(f"Unsupported fs command: {command}", EXIT_USAGE)
