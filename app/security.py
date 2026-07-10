def format_error_response(exc: Exception) -> dict:
    """Return a stable error envelope for all public MCP tools."""
    if isinstance(exc, PermissionError):
        code = "POLICY_BLOCKED"
        suggestion = "Check HOST_WORKSPACE_DIR and HOST_COMMAND_POLICY."
    elif isinstance(exc, FileNotFoundError):
        code = "FILE_NOT_FOUND"
        suggestion = "Check the requested path relative to HOST_WORKSPACE_DIR."
    elif isinstance(exc, TimeoutError):
        code = "TIMEOUT"
        suggestion = "Use a shorter command or increase MAX_TIMEOUT_SECONDS on the server."
    elif isinstance(exc, (TypeError, ValueError)):
        code = "INVALID_ARGUMENT"
        suggestion = "Check the tool arguments and configured limits."
    else:
        code = "INTERNAL_ERROR"
        suggestion = "Check logs/gateway.log and logs/server.log."

    return {
        "ok": False,
        "error": {
            "code": code,
            "message": str(exc),
            "suggestion": suggestion,
        },
    }
