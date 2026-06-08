import hmac
from app.config import GATEWAY_TOKEN

def verify_token(token: str = "") -> bool:
    """Verifies the authorization token securely using constant-time comparison."""
    if not GATEWAY_TOKEN:
        return False  # Do not allow any execution if token is not set
    return hmac.compare_digest(str(token), str(GATEWAY_TOKEN))

def require_token(token: str = "") -> None:
    """Raises PermissionError if token verification fails."""
    if not verify_token(token):
        raise PermissionError("Invalid or missing GATEWAY_TOKEN.")
