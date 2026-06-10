from pathlib import Path

import app.config


def resolve_agent_path(user_path: str) -> Path:
    p = Path(user_path).expanduser()
    if not p.is_absolute():
        p = app.config.AGENT_WORKSPACE_DIR / p
    resolved = p.resolve()

    if app.config.AGENT_RESTRICT_TO_WORKSPACE:
        try:
            resolved.relative_to(app.config.AGENT_WORKSPACE_DIR)
        except ValueError:
            raise PermissionError(
                f"Access denied. Path '{user_path}' is outside the agent workspace directory "
                f"'{app.config.AGENT_WORKSPACE_DIR}'."
            )

    return resolved
