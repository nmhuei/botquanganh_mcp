import hmac

from app.config import GATEWAY_TOKEN, REQUIRE_AUTH


def verify_token(token: str | None = None) -> bool:
    """Verify the authorization token using a constant-time comparison."""
    if not REQUIRE_AUTH:
        return True
    if not GATEWAY_TOKEN:
        return False
    candidate = token if token is not None else str()
    return hmac.compare_digest(candidate, GATEWAY_TOKEN)


def require_token(token: str | None = None) -> None:
    """Raise PermissionError when token verification fails."""
    if not verify_token(token):
        raise PermissionError("Invalid or missing GATEWAY_TOKEN.")
