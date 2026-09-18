from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class QtBindingError(RuntimeError):
    """Raised when the Qt desktop dependency cannot be imported."""


@dataclass(frozen=True)
class QtBindings:
    QtCore: Any
    QtGui: Any
    QtWidgets: Any


def load_qt_bindings() -> QtBindings:
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError as exc:
        raise QtBindingError(
            "Cannot launch bqa ui because PySide6-Essentials is unavailable. "
            "Re-run the project install step so the desktop UI dependency is installed."
        ) from exc
    return QtBindings(QtCore=QtCore, QtGui=QtGui, QtWidgets=QtWidgets)
