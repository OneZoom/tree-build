import logging
import math
import random

import dendropy

from oz_tree_build.taxon_mapping_and_popularity.tree_props.sliding_window import prop_sliding_window


def do_prop_sliding_window(nwk, local_mean_width=5):
    t = dendropy.Tree.get(
        data=nwk,
        schema="newick",
        suppress_leaf_node_taxa=True,
        suppress_internal_node_taxa=True,
    )
    assert prop_sliding_window(t, local_mean_width=local_mean_width) == "sliding_window"

    # Traverse tree, returning all periods
    return [(n.label, getattr(n, "date", None), n.sliding_window) for n in t.preorder_node_iter()]


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


def expected_results(dists, local_mean_width):
    """
    Compute expected sliding_window values from a linear caterpillar tree built
    from dists, where dists[k] is the branch length of node nk, nk's parent is
    n(k+1), and n(len-1) is the root.

    Traversal order is preorder: root (n_last) down to leaf (n0). The window
    walks up to local_mean_width ancestors, but stops at the root (whose own
    edge length is never counted because its loop iteration breaks at the
    parent check) and at any None / negative edge length along the way. A node
    whose own edge length is exactly 0 short-circuits to 0; a node that
    contributes nothing to the window (root, or missing edge length) returns
    0.0.
    """
    n = len(dists)

    def node_sw(k):
        if dists[k] == 0:
            return 0
        window = []
        kk = k
        for _ in range(local_mean_width):
            if kk >= n - 1:
                break
            if dists[kk] is None or dists[kk] < 0:
                break
            window.append(dists[kk])
            kk += 1
        if not window:
            return 0.0
        return math.log(dists[k] / (sum(window) / len(window)))

    return [(f"n{i}", None, node_sw(i)) for i in range(n - 1, -1, -1)]


def test_local_mean_width():
    """local_mean_width param honoured"""
    dists = [random.randrange(10, 100) for _ in range(20)]
    tree_str = generate_tree(dists)

    assert do_prop_sliding_window(tree_str) == expected_results(dists, local_mean_width=5)
    assert do_prop_sliding_window(tree_str, local_mean_width=3) == expected_results(dists, local_mean_width=3)
    assert expected_results(dists, 5) != expected_results(dists, 3)


def test_missing_branch_length(caplog):
    """Nodes with missing branch length get sliding_window 0.0 and emit a warning"""
    dists = [random.randrange(10, 100) for _ in range(20)]
    dists[10] = None
    tree_str = generate_tree(dists)

    with caplog.at_level(
        logging.WARNING, logger="oz_tree_build.taxon_mapping_and_popularity.tree_props.sliding_window"
    ):
        result = do_prop_sliding_window(tree_str, local_mean_width=3)

    assert result == expected_results(dists, local_mean_width=3)
    assert any("n10" in r.message and r.levelno == logging.WARNING for r in caplog.records)


def test_zero_branch_length():
    """Nodes with edge length == 0 short-circuit to sliding_window 0 without affecting siblings"""
    dists = [random.randrange(10, 100) for _ in range(20)]
    dists[10] = 0
    tree_str = generate_tree(dists)

    result = do_prop_sliding_window(tree_str, local_mean_width=3)

    assert result == expected_results(dists, local_mean_width=3)
    # n10 is at preorder index 9 and was given dist 0, so it should be exactly 0.
    assert result[9] == ("n10", None, 0)
