import ete4

from oz_tree_build.tree_build.build_oz_tree import NWK_READ_PARSER
from oz_tree_build.tree_build.infer_ages import infer_ages
from oz_tree_build.tree_build.tree_props.geological import GEOLOGICAL_PERIODS, prop_geological


def do_prop_geological(nwk, date_tree=True):
    t = ete4.Tree(nwk, parser=NWK_READ_PARSER)
    # Our tree needs to have the date property set for this to work
    if date_tree:
        infer_ages(t, None)
    assert prop_geological(t) == "geological"

    # Traverse tree, returning all periods
    return [(n.name, n.props.get("date"), n.props["geological"]) for n in t.traverse()]


def test_undated_tree():
    """Undated trees get None set"""
    assert do_prop_geological("(A:10)B;", date_tree=False) == [
        ("B", None, None),
        ("A", None, None),
    ]


def test_incomplete_date_tree():
    """If not all dates set, we do what we can"""
    assert do_prop_geological("((C:5,D:4)B)A:15;") == [
        ("A", None, None),
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
