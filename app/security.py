from app.error_contract import format_exception_error


def format_error_response(exc: Exception) -> dict:
    """Return the shared stable error envelope for public MCP and REST APIs."""
    return format_exception_error(exc)
