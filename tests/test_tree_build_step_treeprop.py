import logging
import math
import random

import ete4

from oz_tree_build.tree_build.step_treeprop import (
    GEOLOGICAL_PERIODS,
    treeprop_geological,
    treeprop_sliding_window,
    treeprop_weighted_mean,
)


def set_ages_from_dist(tree):
    """
    Postorder pass: leaves get age 0, interior nodes get max(child.age + child.dist).
    If any child has an unknown age or dist, the parent's age becomes None.
    """
    for node in tree.traverse("postorder"):
        if node.is_leaf:
            node.props["age"] = 0
            continue
        parent_age = 0
        for c in node.children:
            if c.props.get("age") is None or c.dist is None:
                parent_age = None
                break
            new_age = c.props["age"] + c.dist
            if new_age > parent_age:
                parent_age = new_age
        node.props["age"] = parent_age


def do_treeprop_geological(nwk, date_tree=True):
    t = ete4.Tree(nwk, parser=1)
    # Our tree needs to have the age prop set for this to work
    if date_tree:
        set_ages_from_dist(t)
    assert treeprop_geological(t) == "geological"

    # Traverse tree, returning all periods
    return [(n.name, n.props.get("age"), n.props["geological"]) for n in t.traverse("preorder")]


def test_undated_tree():
    """Undated trees get 0 set"""
    assert do_treeprop_geological("(A:10)B;", date_tree=False) == [
        ("B", None, 0),
        ("A", None, 0),
    ]


def test_incomplete_date_tree():
    """If not all dates set, we do what we can"""
    assert do_treeprop_geological("((C:5,D:4)B)A:15;") == [
        ("A", None, 0),
        ("B", 5.0, 4),
        ("C", 0, 1),
        ("D", 0, 1),
    ]


def test_complete_date_tree():
    """If all dates set"""
    assert do_treeprop_geological("((C:5,D:4)B:10)A:15;") == [
        ("A", 15.0, 5),
        ("B", 5.0, 4),
        ("C", 0, 1),
        ("D", 0, 1),
    ]


def test_period_inclusive():
    """Mya ranges are incclusive"""

    def get_period(x):
        p = GEOLOGICAL_PERIODS[do_treeprop_geological(f"(B:{x})A;")[0][2]]
        return (p["period"], p["epoch"], p["mya_start"])

    assert get_period(520.99) == ("Cambrian", "Series 2", 521)
    assert get_period(521) == ("Cambrian", "Series 2", 521)
    assert get_period(521.01) == ("Cambrian", "Terreneuvian", 538.8)


#######


def do_treeprop_weighted_mean(nwk, weighting=0.8):
    t = ete4.Tree(nwk, parser=1)
    assert treeprop_weighted_mean(t, weighting=weighting) == "weighted_mean_ratio"

    # Traverse tree, returning all periods
    return [(n.name, n.props.get("date"), n.props["weighted_mean_ratio"]) for n in t.traverse("preorder")]


def generate_tree(dists):
    tree_str = ""
    for i, d in enumerate(dists):
        if tree_str != "":
            tree_str = f"({tree_str})"
        tree_str += f"n{i}"
        if d is not None:
            tree_str += f":{d}"
    tree_str += ";"
    return tree_str


def expected_results_wm(dists, weighting):
    """
    Compute expected weighted_mean_ratio values for a linear caterpillar tree
    built from dists, where dists[k] is the branch length of node nk, nk's
    parent is n(k+1), and n(len-1) is the root.

    Traversal is preorder, so results start at the root (n_last) and walk
    down to the leaf (n0). The root and any node with a missing branch
    length get weighted_mean and weighted_mean_ratio of 0.0; that 0.0 then
    feeds back into the recurrence for descendants like any other value,
    so a single missing dist no longer poisons the whole subtree below it.
    """
    n = len(dists)
    weighted_mean = [None] * n

    # Walk from root (index n-1) down to leaf (index 0)
    for i in range(n - 1, -1, -1):
        if i == n - 1 or dists[i] is None:
            weighted_mean[i] = 0.0
        else:
            weighted_mean[i] = (dists[i] + weighted_mean[i + 1] * weighting) / (1 + weighting)

    results = []
    for i in range(n - 1, -1, -1):
        if i == n - 1 or dists[i] is None:
            ratio = 0.0
        else:
            ratio = dists[i] / weighted_mean[i]
        results.append((f"n{i}", None, ratio))
    return results


def test_weighting():
    """weighting param honoured"""
    dists = [random.randrange(10, 100) for _ in range(20)]
    tree_str = generate_tree(dists)

    assert do_treeprop_weighted_mean(tree_str) == expected_results_wm(dists, weighting=0.8)
    assert do_treeprop_weighted_mean(tree_str, weighting=3) == expected_results_wm(dists, weighting=3)
    assert expected_results_wm(dists, 0.8) != expected_results_wm(dists, 3)


def test_missing_branch_length(caplog):
    """Nodes with missing branch length get a 0.0 weighted_mean and emit a warning.

    The missing node's 0.0 feeds back into the recurrence for its descendants
    like any other value, so only the missing node itself (and the root, which
    is always 0.0) shows a zero ratio.
    """
    dists = [random.randrange(10, 100) for _ in range(20)]
    dists[10] = None
    tree_str = generate_tree(dists)

    with caplog.at_level(logging.WARNING, logger="oz_tree_build.taxon_mapping_and_popularity.tree_props.weighted_mean"):
        result = do_treeprop_weighted_mean(tree_str, weighting=3)

    assert result == expected_results_wm(dists, weighting=3)
    # Preorder visits n19..n0. Only the root (index 0 → n19) and the missing
    # node (index 9 → n10) have ratio 0.0; descendants of n10 compute normally.
    assert [i for i, x in enumerate(result) if x[2] == 0.0] == [0, 9]
    assert any("n10" in r.message and r.levelno == logging.WARNING for r in caplog.records)


####################


def do_treeprop_sliding_window(nwk, local_mean_width=5):
    t = ete4.Tree(nwk, parser=1)
    assert treeprop_sliding_window(t, local_mean_width=local_mean_width) == "sliding_window"

    # Traverse tree, returning all periods
    return [(n.name, n.props.get("date"), n.props["sliding_window"]) for n in t.traverse("preorder")]


def expected_results_sw(dists, local_mean_width):
    """
    Compute expected sliding_window values from a linear caterpillar tree built
    from dists, where dists[k] is the branch length of node nk, nk's parent is
    n(k+1), and n(len-1) is the root.

    Traversal order is preorder: root (n_last) down to leaf (n0). The window
    walks up to local_mean_width ancestors (stopping at the root, whose own
    edge length is never counted, or at any None / negative edge length) and
    up to local_mean_width descendants downwards (in this linear tree a single
    chain; again stopping at a None / negative edge length). A node whose own
    edge length is exactly 0 short-circuits to 0; a None / negative own edge
    length short-circuits to 0.0; a node that contributes nothing to the
    window returns 0.0.
    """
    n = len(dists)

    def node_sw(k):
        if dists[k] == 0:
            return 0
        if dists[k] is None or dists[k] < 0:
            return 0.0
        window = []
        kk = k
        for _ in range(local_mean_width):
            if kk >= n - 1:
                break
            if dists[kk] is None or dists[kk] < 0:
                break
            window.append(dists[kk])
            kk += 1
        kk = k - 1
        for _ in range(local_mean_width):
            if kk < 0:
                break
            if dists[kk] is None or dists[kk] < 0:
                break
            window.append(dists[kk])
            kk -= 1
        if not window:
            return 0.0
        return math.log(dists[k] / (sum(window) / len(window)))

    return [(f"n{i}", None, node_sw(i)) for i in range(n - 1, -1, -1)]


def test_local_mean_width():
    """local_mean_width param honoured"""
    dists = [random.randrange(10, 100) for _ in range(20)]
    tree_str = generate_tree(dists)

    assert do_treeprop_sliding_window(tree_str) == expected_results_sw(dists, local_mean_width=5)
    assert do_treeprop_sliding_window(tree_str, local_mean_width=3) == expected_results_sw(dists, local_mean_width=3)
    assert expected_results_sw(dists, 5) != expected_results_sw(dists, 3)


def test_missing_branch_length(caplog):
    """Nodes with missing branch length get sliding_window 0.0 and emit a warning"""
    dists = [random.randrange(10, 100) for _ in range(20)]
    dists[10] = None
    tree_str = generate_tree(dists)

    with caplog.at_level(
        logging.WARNING, logger="oz_tree_build.taxon_mapping_and_popularity.tree_props.sliding_window"
    ):
        result = do_treeprop_sliding_window(tree_str, local_mean_width=3)

    assert result == expected_results_sw(dists, local_mean_width=3)
    assert any("n10" in r.message and r.levelno == logging.WARNING for r in caplog.records)


def test_zero_branch_length():
    """Nodes with edge length == 0 short-circuit to sliding_window 0 without affecting siblings"""
    dists = [random.randrange(10, 100) for _ in range(20)]
    dists[10] = 0
    tree_str = generate_tree(dists)

    result = do_treeprop_sliding_window(tree_str, local_mean_width=3)

    assert result == expected_results_sw(dists, local_mean_width=3)
    # n10 is at preorder index 9 and was given dist 0, so it should be exactly 0.
    assert result[9] == ("n10", None, 0)
