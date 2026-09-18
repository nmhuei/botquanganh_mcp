"""Focused Tk desktop views used by the desktop coordinator."""

from app.cli.desktop_views.activity import ActivityView
from app.cli.desktop_views.runtime import RuntimePresentation, RuntimeView, runtime_presentation
from app.cli.desktop_views.workspace_logs import WorkspaceLogView

__all__ = [
    "ActivityView",
    "RuntimePresentation",
    "RuntimeView",
    "WorkspaceLogView",
    "runtime_presentation",
]
