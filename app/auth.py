def verify_token(token: str = "") -> bool:
    """Verifies the token. Always returns True as token authentication is disabled."""
    return True

def require_token(token: str = "") -> None:
    """Passes if verification succeeds, otherwise raises PermissionError. Always passes."""
    pass


