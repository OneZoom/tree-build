import dendropy

from oz_tree_build.taxon_mapping_and_popularity.tree_props.geological import GEOLOGICAL_PERIODS, prop_geological


def set_ages_from_dist(tree):
    """
    Postorder pass: leaves get age 0, interior nodes get max(child.age + child.edge.length).
    If any child has an unknown age or edge length, the parent's age becomes None.
    """
    for node in tree.postorder_node_iter():
        if node.is_leaf():
            node.age = 0
            continue
        parent_age = 0
        for c in node.child_node_iter():
            if getattr(c, "age", None) is None or c.edge.length is None:
                parent_age = None
                break
            new_age = c.age + c.edge.length
            if new_age > parent_age:
                parent_age = new_age
        node.age = parent_age


def do_prop_geological(nwk, date_tree=True):
    t = dendropy.Tree.get(
        data=nwk,
        schema="newick",
        suppress_leaf_node_taxa=True,
        suppress_internal_node_taxa=True,
    )
    # Our tree needs to have the date attribute set for this to work
    if date_tree:
        set_ages_from_dist(t)
    assert prop_geological(t) == "geological"

    # Traverse tree, returning all periods
    return [(n.label, getattr(n, "age", None), n.geological) for n in t.preorder_node_iter()]


def test_undated_tree():
    """Undated trees get 0 set"""
    assert do_prop_geological("(A:10)B;", date_tree=False) == [
        ("B", None, 0),
        ("A", None, 0),
    ]


def test_incomplete_date_tree():
    """If not all dates set, we do what we can"""
    assert do_prop_geological("((C:5,D:4)B)A:15;") == [
        ("A", None, 0),
        ("B", 5.0, 3),
        ("C", 0, 1),
        ("D", 0, 1),
    ]


def test_complete_date_tree():
    """If all dates set"""
    assert do_prop_geological("((C:5,D:4)B:10)A:15;") == [
        ("A", 15.0, 4),
        ("B", 5.0, 3),
        ("C", 0, 1),
        ("D", 0, 1),
    ]


def test_period_inclusive():
    """Mya ranges are incclusive"""

    def get_period(x):
        return GEOLOGICAL_PERIODS[do_prop_geological(f"(B:{x})A;")[0][2]]

    assert get_period(520.99) == {"period": "Cambrian", "epoch": "Series 2", "mya_start": 521}
    assert get_period(521) == {"period": "Cambrian", "epoch": "Series 2", "mya_start": 521}
    assert get_period(521.01) == {"period": "Cambrian", "epoch": "Terreneuvian", "mya_start": 538.8}
