"""Qt item models used by the BQA Center QML frontend."""

from __future__ import annotations

from typing import Any, Iterable

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, QByteArray


class KeyedListModel(QAbstractListModel):
    """Small keyed model with cheap common live-update paths.

    Live streams usually prepend a few rows or update values in place. Those
    cases use beginInsertRows/dataChanged instead of resetting the whole view.
    Complex user-driven filter/order changes fall back to a model reset.
    """

    def __init__(self, *, key_role: str, roles: Iterable[str]) -> None:
        super().__init__()
        self.key_role = key_role
        ordered = list(dict.fromkeys([key_role, *roles]))
        self._roles = ordered
        self._role_ids = {
            Qt.UserRole + index + 1: name for index, name in enumerate(ordered)
        }
        self._role_by_name = {name: role for role, name in self._role_ids.items()}
        self._rows: list[dict[str, Any]] = []

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            role: QByteArray(name.encode("utf-8"))
            for role, name in self._role_ids.items()
        }

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        name = self._role_ids.get(role)
        if name is None:
            return None
        return self._rows[index.row()].get(name)

    def get(self, row: int) -> dict[str, Any]:
        return dict(self._rows[row]) if 0 <= row < len(self._rows) else {}

    def find(self, key: str) -> int:
        for index, row in enumerate(self._rows):
            if str(row.get(self.key_role) or "") == str(key):
                return index
        return -1

    def row_for_key(self, key: str) -> dict[str, Any]:
        index = self.find(key)
        return self.get(index) if index >= 0 else {}

    def rows(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows]

    def _emit_updates(self, new_rows: list[dict[str, Any]]) -> None:
        for index, (old, new) in enumerate(zip(self._rows, new_rows)):
            if old == new:
                continue
            changed = [
                self._role_by_name[name]
                for name in self._roles
                if old.get(name) != new.get(name)
            ]
            self._rows[index] = dict(new)
            top = self.index(index, 0)
            self.dataChanged.emit(top, top, changed)

    def sync(self, rows: Iterable[dict[str, Any]]) -> None:
        desired = [dict(row) for row in rows]
        old_keys = [str(row.get(self.key_role) or "") for row in self._rows]
        new_keys = [str(row.get(self.key_role) or "") for row in desired]

        if old_keys == new_keys:
            self._emit_updates(desired)
            return

        # Common streaming case: one or more rows appear at the front.
        if old_keys and len(new_keys) >= len(old_keys):
            tail = new_keys[-len(old_keys):]
            if tail == old_keys:
                count = len(new_keys) - len(old_keys)
                if count:
                    self.beginInsertRows(QModelIndex(), 0, count - 1)
                    self._rows[0:0] = desired[:count]
                    self.endInsertRows()
                self._emit_updates(desired)
                return

        # Common cache trim/filter case: remove a prefix while preserving order.
        if new_keys and len(old_keys) >= len(new_keys):
            tail = old_keys[-len(new_keys):]
            if tail == new_keys:
                count = len(old_keys) - len(new_keys)
                if count:
                    self.beginRemoveRows(QModelIndex(), 0, count - 1)
                    del self._rows[:count]
                    self.endRemoveRows()
                self._emit_updates(desired)
                return

        self.beginResetModel()
        self._rows = desired
        self.endResetModel()


SESSION_ROLES = (
    "displayName",
    "sessionState",
    "last",
    "unread",
    "running",
    "tracked",
    "closed",
)

OPERATION_ROLES = (
    "utc",
    "status",
    "command",
    "exit",
    "duration",
    "chatId",
    "cwd",
    "stdout",
    "stderr",
    "metadata",
    "human",
)

LOG_ROLES = (
    "utc",
    "severity",
    "category",
    "action",
    "outcome",
    "duration",
    "chatId",
    "operationId",
    "summary",
    "metadata",
    "payloadText",
)


class SessionListModel(KeyedListModel):
    def __init__(self) -> None:
        super().__init__(key_role="chatId", roles=SESSION_ROLES)


class OperationListModel(KeyedListModel):
    def __init__(self) -> None:
        super().__init__(key_role="operationId", roles=OPERATION_ROLES)


class LogListModel(KeyedListModel):
    def __init__(self) -> None:
        super().__init__(key_role="eventId", roles=LOG_ROLES)


WORKSPACE_ROLES = (
    "label",
    "path",
    "workspaceState",
    "archived",
    "metaOk",
    "createdAt",
    "lastActive",
    "lastActiveEpoch",
    "sizeBytes",
    "sizeText",
    "events",
    "operations",
    "failures",
)

ATTENTION_ROLES = (
    "severity",
    "title",
    "detail",
    "action",
)

HEALTH_METRIC_ROLES = (
    "label",
    "value",
    "detail",
)

DOCTOR_CHECK_ROLES = (
    "name",
    "status",
    "message",
)

SECURITY_ROLES = (
    "label",
    "value",
    "tone",
    "detail",
)

CONFIG_CHECK_ROLES = (
    "name",
    "status",
    "message",
)

RUNTIME_LOG_ROLES = (
    "source",
    "timestamp",
    "line",
)


class WorkspaceListModel(KeyedListModel):
    def __init__(self) -> None:
        super().__init__(key_role="chatId", roles=WORKSPACE_ROLES)


class AttentionListModel(KeyedListModel):
    def __init__(self) -> None:
        super().__init__(key_role="itemId", roles=ATTENTION_ROLES)


class HealthMetricListModel(KeyedListModel):
    def __init__(self) -> None:
        super().__init__(key_role="itemId", roles=HEALTH_METRIC_ROLES)


class DoctorCheckListModel(KeyedListModel):
    def __init__(self) -> None:
        super().__init__(key_role="name", roles=DOCTOR_CHECK_ROLES)


class SecurityListModel(KeyedListModel):
    def __init__(self) -> None:
        super().__init__(key_role="itemId", roles=SECURITY_ROLES)


class ConfigCheckListModel(KeyedListModel):
    def __init__(self) -> None:
        super().__init__(key_role="name", roles=CONFIG_CHECK_ROLES)


class RuntimeLogListModel(KeyedListModel):
    def __init__(self) -> None:
        super().__init__(key_role="rowId", roles=RUNTIME_LOG_ROLES)
