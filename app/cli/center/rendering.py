"""Incremental Treeview row reconciliation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class TreeRow:
    iid: str
    values: tuple[Any, ...] = ()
    text: str = ""
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class TreeDiff:
    inserted: int = 0
    updated: int = 0
    deleted: int = 0
    moved: int = 0


def reconcile_tree_rows(tree: Any, rows: Iterable[TreeRow]) -> TreeDiff:
    """Reconcile keyed rows without clearing the Treeview.

    Existing selection and scroll position stay owned by Tk because stable rows
    are updated in place. Reordering uses the Treeview move operation where
    available.
    """
    desired = list(rows)
    desired_ids = [row.iid for row in desired]
    desired_set = set(desired_ids)
    existing = list(tree.get_children())
    existing_set = set(existing)

    deleted = 0
    for iid in existing:
        if iid not in desired_set:
            tree.delete(iid)
            deleted += 1

    inserted = updated = moved = 0
    for index, row in enumerate(desired):
        if row.iid not in existing_set:
            tree.insert(
                "",
                "end",
                iid=row.iid,
                text=row.text,
                values=row.values,
                tags=row.tags,
            )
            inserted += 1
        else:
            tree.item(
                row.iid,
                text=row.text,
                values=row.values,
                tags=row.tags,
            )
            updated += 1
        try:
            current = list(tree.get_children()).index(row.iid)
        except (ValueError, AttributeError):
            current = index
        if current != index and hasattr(tree, "move"):
            tree.move(row.iid, "", index)
            moved += 1

    return TreeDiff(
        inserted=inserted,
        updated=updated,
        deleted=deleted,
        moved=moved,
    )
