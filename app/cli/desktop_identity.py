from __future__ import annotations

from pathlib import Path


DESKTOP_APP_NAME = "UCS-SecretAgent"
DESKTOP_IDENTITY_TEXT = "UCS // SECRET AGENT"


def desktop_app_icon_path() -> Path:
    return Path(__file__).resolve().parents[2] / "resources" / "ucs-secretagent.png"
