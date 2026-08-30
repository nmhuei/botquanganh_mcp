from app.cli.center.rendering import TreeRow, reconcile_tree_rows


class FakeTree:
    def __init__(self):
        self.rows = {}
        self.order = []
        self.deleted = []
        self.updated = []

    def get_children(self):
        return tuple(self.order)

    def insert(self, _parent, _index, *, iid, text="", values=(), tags=()):
        self.rows[iid] = {"text": text, "values": values, "tags": tags}
        self.order.append(iid)

    def item(self, iid, **values):
        self.rows[iid].update(values)
        self.updated.append(iid)

    def delete(self, iid):
        self.deleted.append(iid)
        self.rows.pop(iid, None)
        self.order.remove(iid)

    def move(self, iid, _parent, index):
        self.order.remove(iid)
        self.order.insert(index, iid)


def test_reconcile_tree_rows_updates_in_place_without_clear_all():
    tree = FakeTree()
    reconcile_tree_rows(
        tree,
        [
            TreeRow("a", values=(1,)),
            TreeRow("b", values=(2,)),
        ],
    )

    diff = reconcile_tree_rows(
        tree,
        [
            TreeRow("a", values=(10,)),
            TreeRow("c", values=(3,)),
        ],
    )

    assert tree.order == ["a", "c"]
    assert tree.rows["a"]["values"] == (10,)
    assert tree.deleted == ["b"]
    assert "a" in tree.updated
    assert diff.inserted == 1
    assert diff.deleted == 1


def test_reconcile_tree_rows_reorders_stable_rows_with_move():
    tree = FakeTree()
    reconcile_tree_rows(tree, [TreeRow("a"), TreeRow("b"), TreeRow("c")])

    diff = reconcile_tree_rows(tree, [TreeRow("c"), TreeRow("a"), TreeRow("b")])

    assert tree.order == ["c", "a", "b"]
    assert diff.moved >= 1
