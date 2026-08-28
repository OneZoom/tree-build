import ete4

from oz_tree_build.tree_build.step_treeprop import (
    GEOLOGICAL_PERIODS,
    treeprop_geological,
)

########################################
# treeprop_geological
########################################


def set_dates_from_dist(tree):
    """
    Postorder pass: leaves get date 0, interior nodes get max(child.date + child.dist).
    If any child has an unknown date or dist, the parent's date becomes None.
    """
    for node in tree.traverse("postorder"):
        if node.is_leaf:
            node.props["date"] = 0
            continue
        parent_date = 0
        for c in node.children:
            if c.props.get("date") is None or c.dist is None:
                parent_date = None
                break
            new_date = c.props["date"] + c.dist
            if new_date > parent_date:
                parent_date = new_date
        node.props["date"] = parent_date


def do_treeprop_geological(nwk, date_tree=True):
    t = ete4.Tree(nwk, parser=1)
    # Our tree needs to have the date prop set for this to work
    if date_tree:
        set_dates_from_dist(t)
    assert treeprop_geological(t) == "geological"

    # Traverse tree, returning all periods
    return [(n.name, n.props.get("date"), n.props["geological"]) for n in t.traverse("preorder")]


class TestTreepropGeological:
    def test_undated_tree(self):
        """Undated trees get 0 set"""
        assert do_treeprop_geological("(A:10)B;", date_tree=False) == [
            ("B", None, 0),
            ("A", None, 0),
        ]

    def test_incomplete_date_tree(self):
        """If not all dates set, we do what we can"""
        assert do_treeprop_geological("((C:5,D:4)B)A:15;") == [
            ("A", None, 0),
            ("B", 5.0, 4),
            ("C", 0, 1),
            ("D", 0, 1),
        ]

    def test_complete_date_tree(self):
        """If all dates set"""
        assert do_treeprop_geological("((C:5,D:4)B:10)A:15;") == [
            ("A", 15.0, 5),
            ("B", 5.0, 4),
            ("C", 0, 1),
            ("D", 0, 1),
        ]

    def test_period_inclusive(self):
        """Mya ranges are incclusive"""

        def get_period(x):
            p = GEOLOGICAL_PERIODS[do_treeprop_geological(f"(B:{x})A;")[0][2]]
            return (p["period"], p["epoch"], p["mya_start"])

        assert get_period(520.99) == ("Cambrian", "Series 2", 521)
        assert get_period(521) == ("Cambrian", "Series 2", 521)
        assert get_period(521.01) == ("Cambrian", "Terreneuvian", 538.8)
