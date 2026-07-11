from __future__ import annotations

from typing import Any, Callable

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.host.executor import execute_host_command
from app.host.files import (
    append_text_file,
    list_directory,
    make_directory,
    read_text_file,
    replace_text_in_file,
    search_text,
    write_text_file,
)
from app.host.policy import inspect_host_command
from app.security import format_error_response

API_PREFIX = "/api/v1"


def _error_status(exc: Exception) -> int:
    if isinstance(exc, FileNotFoundError):
        return 404
    if isinstance(exc, FileExistsError):
        return 409
    if isinstance(exc, PermissionError):
        return 403
    if isinstance(exc, (ValueError, TypeError, NotADirectoryError)):
        return 400
    return 500


def _result_status(result: Any) -> int:
    if not isinstance(result, dict) or result.get("ok", True):
        return 200
    code = str(result.get("error", {}).get("code", ""))
    if code in {"POLICY_BLOCKED", "TARGET_NOT_ALLOWLISTED"}:
        return 403
    if code in {"RUN_NOT_FOUND"}:
        return 404
    if code in {"TIMEOUT", "TIMEOUT_INVALID"}:
        return 408
    if code in {"SCHEMA_INVALID", "UNSUPPORTED_ENCODING", "UNSUPPORTED_LANGUAGE"}:
        return 400
    return 500


async def _call(function: Callable[..., Any], *args: Any, **kwargs: Any) -> JSONResponse:
    try:
        result = await run_in_threadpool(function, *args, **kwargs)
        return JSONResponse(result, status_code=_result_status(result))
    except Exception as exc:
        return JSONResponse(format_error_response(exc), status_code=_error_status(exc))


async def _json_body(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception as exc:
        raise ValueError("Request body must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")
    return payload


def _query_int(request: Request, name: str, default: int | None = None) -> int | None:
    value = request.query_params.get(name)
    if value in {None, ""}:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Query parameter '{name}' must be an integer.") from exc


def _query_bool(request: Request, name: str, default: bool = False) -> bool:
    value = request.query_params.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Query parameter '{name}' must be a boolean.")


async def api_index(_request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "name": "BotQuangAnh Host REST API",
            "version": "v1",
            "openapi": f"{API_PREFIX}/openapi.json",
            "endpoints": [
                {"method": "GET", "path": f"{API_PREFIX}/health"},
                {"method": "GET", "path": f"{API_PREFIX}/capabilities"},
                {"method": "GET", "path": f"{API_PREFIX}/files"},
                {"method": "GET", "path": f"{API_PREFIX}/files/content"},
                {"method": "PUT", "path": f"{API_PREFIX}/files/content"},
                {"method": "PATCH", "path": f"{API_PREFIX}/files/content"},
                {"method": "POST", "path": f"{API_PREFIX}/files/append"},
                {"method": "POST", "path": f"{API_PREFIX}/directories"},
                {"method": "GET", "path": f"{API_PREFIX}/search"},
                {"method": "POST", "path": f"{API_PREFIX}/commands/check"},
                {"method": "POST", "path": f"{API_PREFIX}/commands/run"},
                {"method": "GET", "path": f"{API_PREFIX}/knowledge"},
            ],
        }
    )


async def api_health(_request: Request) -> JSONResponse:
    from app.tools.health import health_check

    return await _call(health_check)


async def api_capabilities(_request: Request) -> JSONResponse:
    from app.tools.health import get_capabilities

    return await _call(get_capabilities)


async def api_list_files(request: Request) -> JSONResponse:
    try:
        path = request.query_params.get("path", ".")
        max_entries = _query_int(request, "max_entries", 500)
        return await _call(list_directory, path, max_entries=max_entries or 500)
    except Exception as exc:
        return JSONResponse(format_error_response(exc), status_code=_error_status(exc))


async def api_read_file(request: Request) -> JSONResponse:
    try:
        path = request.query_params.get("path", "").strip()
        if not path:
            raise ValueError("Query parameter 'path' is required.")
        return await _call(
            read_text_file,
            path,
            start_line=_query_int(request, "start_line"),
            end_line=_query_int(request, "end_line"),
            max_bytes=_query_int(request, "max_bytes"),
        )
    except Exception as exc:
        return JSONResponse(format_error_response(exc), status_code=_error_status(exc))


async def api_write_file(request: Request) -> JSONResponse:
    try:
        body = await _json_body(request)
        path = str(body.get("path", "")).strip()
        if not path:
            raise ValueError("Field 'path' is required.")
        content = body.get("content")
        if not isinstance(content, str):
            raise ValueError("Field 'content' must be a string.")
        return await _call(
            write_text_file,
            path,
            content,
            overwrite=bool(body.get("overwrite", True)),
            create_parents=bool(body.get("create_parents", True)),
        )
    except Exception as exc:
        return JSONResponse(format_error_response(exc), status_code=_error_status(exc))


async def api_replace_file(request: Request) -> JSONResponse:
    try:
        body = await _json_body(request)
        path = str(body.get("path", "")).strip()
        old = body.get("old")
        new = body.get("new")
        if not path:
            raise ValueError("Field 'path' is required.")
        if not isinstance(old, str) or not isinstance(new, str):
            raise ValueError("Fields 'old' and 'new' must be strings.")
        expected_count = int(body.get("expected_count", 1))
        return await _call(
            replace_text_in_file,
            path,
            old,
            new,
            expected_count=expected_count,
        )
    except Exception as exc:
        return JSONResponse(format_error_response(exc), status_code=_error_status(exc))


async def api_append_file(request: Request) -> JSONResponse:
    try:
        body = await _json_body(request)
        path = str(body.get("path", "")).strip()
        content = body.get("content")
        if not path:
            raise ValueError("Field 'path' is required.")
        if not isinstance(content, str):
            raise ValueError("Field 'content' must be a string.")
        return await _call(append_text_file, path, content)
    except Exception as exc:
        return JSONResponse(format_error_response(exc), status_code=_error_status(exc))


async def api_make_directory(request: Request) -> JSONResponse:
    try:
        body = await _json_body(request)
        path = str(body.get("path", "")).strip()
        if not path:
            raise ValueError("Field 'path' is required.")
        return await _call(make_directory, path, parents=bool(body.get("parents", True)))
    except Exception as exc:
        return JSONResponse(format_error_response(exc), status_code=_error_status(exc))


async def api_search(request: Request) -> JSONResponse:
    try:
        query = request.query_params.get("query", "").strip()
        if not query:
            raise ValueError("Query parameter 'query' is required.")
        return await _call(
            search_text,
            query,
            path=request.query_params.get("path", "."),
            case_sensitive=_query_bool(request, "case_sensitive", False),
            max_results=_query_int(request, "max_results", 100) or 100,
        )
    except Exception as exc:
        return JSONResponse(format_error_response(exc), status_code=_error_status(exc))


async def api_check_command(request: Request) -> JSONResponse:
    try:
        body = await _json_body(request)
        command = str(body.get("command", "")).strip()
        if not command:
            raise ValueError("Field 'command' is required.")
        return await _call(lambda: {"ok": True, **inspect_host_command(command)})
    except Exception as exc:
        return JSONResponse(format_error_response(exc), status_code=_error_status(exc))


async def api_run_command(request: Request) -> JSONResponse:
    try:
        body = await _json_body(request)
        command = str(body.get("command", "")).strip()
        if not command:
            raise ValueError("Field 'command' is required.")
        timeout_seconds = int(body.get("timeout_seconds", 30))
        cwd = body.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            raise ValueError("Field 'cwd' must be a string or null.")
        return await _call(
            execute_host_command,
            command,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        return JSONResponse(format_error_response(exc), status_code=_error_status(exc))


async def api_knowledge(request: Request) -> JSONResponse:
    try:
        from app.tools.host_knowledge import host_knowledge

        return await _call(
            host_knowledge,
            section=request.query_params.get("section", "overview"),
            query=request.query_params.get("query", ""),
            category=request.query_params.get("category", ""),
            available_only=_query_bool(request, "available_only", True),
            include_versions=_query_bool(request, "include_versions", False),
            include_uncatalogued=_query_bool(request, "include_uncatalogued", False),
            refresh=_query_bool(request, "refresh", False),
        )
    except Exception as exc:
        return JSONResponse(format_error_response(exc), status_code=_error_status(exc))


def openapi_document() -> dict[str, Any]:
    json_object = {"type": "object", "additionalProperties": True}
    error_responses = {
        "400": {"description": "Invalid request"},
        "401": {"description": "Authentication required"},
        "403": {"description": "Operation blocked"},
        "500": {"description": "Internal error"},
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "BotQuangAnh Host REST API",
            "version": "1.0.0",
            "description": "REST access to the same host services exposed through MCP.",
        },
        "servers": [{"url": "/"}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"},
                "gatewayToken": {"type": "apiKey", "in": "header", "name": "X-Gateway-Token"},
            },
            "schemas": {"GenericResponse": json_object},
        },
        "security": [{"bearerAuth": []}, {"gatewayToken": []}],
        "paths": {
            f"{API_PREFIX}": {"get": {"summary": "List REST endpoints", "responses": {"200": {"description": "API index"}}}},
            f"{API_PREFIX}/health": {"get": {"summary": "Service health", "responses": {"200": {"description": "Health response"}, **error_responses}}},
            f"{API_PREFIX}/capabilities": {"get": {"summary": "Service capabilities", "responses": {"200": {"description": "Capabilities"}, **error_responses}}},
            f"{API_PREFIX}/files": {"get": {"summary": "List a directory", "parameters": [{"name": "path", "in": "query", "schema": {"type": "string", "default": "."}}, {"name": "max_entries", "in": "query", "schema": {"type": "integer", "default": 500}}], "responses": {"200": {"description": "Directory listing"}, **error_responses}}},
            f"{API_PREFIX}/files/content": {
                "get": {"summary": "Read a text file", "parameters": [{"name": "path", "in": "query", "required": True, "schema": {"type": "string"}}], "responses": {"200": {"description": "File content"}, **error_responses}},
                "put": {"summary": "Create or overwrite a text file", "requestBody": {"required": True, "content": {"application/json": {"schema": json_object}}}, "responses": {"200": {"description": "Write result"}, **error_responses}},
                "patch": {"summary": "Replace text in a file", "requestBody": {"required": True, "content": {"application/json": {"schema": json_object}}}, "responses": {"200": {"description": "Replace result"}, **error_responses}},
            },
            f"{API_PREFIX}/files/append": {"post": {"summary": "Append text to a file", "requestBody": {"required": True, "content": {"application/json": {"schema": json_object}}}, "responses": {"200": {"description": "Append result"}, **error_responses}}},
            f"{API_PREFIX}/directories": {"post": {"summary": "Create a directory", "requestBody": {"required": True, "content": {"application/json": {"schema": json_object}}}, "responses": {"200": {"description": "Directory result"}, **error_responses}}},
            f"{API_PREFIX}/search": {"get": {"summary": "Search text recursively", "parameters": [{"name": "query", "in": "query", "required": True, "schema": {"type": "string"}}, {"name": "path", "in": "query", "schema": {"type": "string", "default": "."}}], "responses": {"200": {"description": "Search results"}, **error_responses}}},
            f"{API_PREFIX}/commands/check": {"post": {"summary": "Inspect a host command", "requestBody": {"required": True, "content": {"application/json": {"schema": json_object}}}, "responses": {"200": {"description": "Policy result"}, **error_responses}}},
            f"{API_PREFIX}/commands/run": {"post": {"summary": "Run a host command", "requestBody": {"required": True, "content": {"application/json": {"schema": json_object}}}, "responses": {"200": {"description": "Execution result"}, **error_responses}}},
            f"{API_PREFIX}/knowledge": {"get": {"summary": "Read host guides and tool inventory", "parameters": [{"name": "section", "in": "query", "schema": {"type": "string", "default": "overview"}}, {"name": "query", "in": "query", "schema": {"type": "string"}}], "responses": {"200": {"description": "Knowledge result"}, **error_responses}}},
            f"{API_PREFIX}/openapi.json": {"get": {"summary": "OpenAPI document", "security": [], "responses": {"200": {"description": "OpenAPI 3.1 document"}}}},
        },
    }


async def api_openapi(_request: Request) -> JSONResponse:
    return JSONResponse(openapi_document())


def rest_routes() -> list[Route]:
    return [
        Route(API_PREFIX, api_index, methods=["GET"]),
        Route(f"{API_PREFIX}/health", api_health, methods=["GET"]),
        Route(f"{API_PREFIX}/capabilities", api_capabilities, methods=["GET"]),
        Route(f"{API_PREFIX}/files", api_list_files, methods=["GET"]),
        Route(f"{API_PREFIX}/files/content", api_read_file, methods=["GET"]),
        Route(f"{API_PREFIX}/files/content", api_write_file, methods=["PUT"]),
        Route(f"{API_PREFIX}/files/content", api_replace_file, methods=["PATCH"]),
        Route(f"{API_PREFIX}/files/append", api_append_file, methods=["POST"]),
        Route(f"{API_PREFIX}/directories", api_make_directory, methods=["POST"]),
        Route(f"{API_PREFIX}/search", api_search, methods=["GET"]),
        Route(f"{API_PREFIX}/commands/check", api_check_command, methods=["POST"]),
        Route(f"{API_PREFIX}/commands/run", api_run_command, methods=["POST"]),
        Route(f"{API_PREFIX}/knowledge", api_knowledge, methods=["GET"]),
        Route(f"{API_PREFIX}/openapi.json", api_openapi, methods=["GET"]),
    ]


def install_rest_routes(app: Any) -> None:
    existing = {getattr(route, "path", None) for route in app.router.routes}
    routes = [route for route in rest_routes() if route.path not in existing]
    # Put REST routes before the MCP route so generic mounts cannot shadow them.
    app.router.routes[1:1] = routes
