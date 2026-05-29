import logging
import math
import random

import ete4

from oz_tree_build.tree_build.build_oz_tree import NWK_READ_PARSER
from oz_tree_build.tree_build.tree_props.sliding_window import prop_sliding_window


def do_prop_sliding_window(nwk, local_mean_width=5):
    t = ete4.Tree(nwk, parser=NWK_READ_PARSER)
    assert prop_sliding_window(t, local_mean_width=local_mean_width) == "sliding_window"

    # Traverse tree, returning all periods
    return [(n.name, n.props.get("date"), n.props["sliding_window"]) for n in t.traverse()]


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

    Traversal order is preorder: root (n_last) down to leaf (n0).
    For each node nk the window walks up local_mean_width ancestors inclusive,
    which corresponds to dists[k : k+local_mean_width].
    """
    n = len(dists)

    def node_sw(k):
        window = dists[k : k + local_mean_width]
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
    """Nodes with missing branch length get None sliding_window and emit a warning"""
    dists = [random.randrange(10, 100) for _ in range(20)]
    dists[10] = None
    tree_str = generate_tree(dists)

    with caplog.at_level(logging.WARNING, logger="oz_tree_build.tree_build.tree_props.sliding_window"):
        result = do_prop_sliding_window(tree_str, local_mean_width=3)

    assert [i for i, x in enumerate(result) if x[2] is None] == [9]
    assert any("n10" in r.message and r.levelno == logging.WARNING for r in caplog.records)
