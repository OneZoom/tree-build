import logging
import random

import ete4

from oz_tree_build.tree_build.build_oz_tree import NWK_READ_PARSER
from oz_tree_build.tree_build.tree_props.weighted_mean import prop_weighted_mean


def do_prop_weighted_mean(nwk, weighting=0.8):
    t = ete4.Tree(nwk, parser=NWK_READ_PARSER)
    assert prop_weighted_mean(t, weighting=weighting) == "weighted_mean_ratio"

    # Traverse tree, returning all periods
    return [(n.name, n.props.get("date"), n.props["weighted_mean_ratio"]) for n in t.traverse()]


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


def expected_results(dists, weighting):
    """
    Compute expected weighted_mean_ratio values for a linear caterpillar tree
    built from dists, where dists[k] is the branch length of node nk, nk's
    parent is n(k+1), and n(len-1) is the root.

    Traversal is preorder, so results start at the root (n_last) and walk
    down to the leaf (n0). A None branch length propagates None into both
    the weighted_mean and weighted_mean_ratio of the node itself and all
    its descendants, since the recurrence depends on the parent.
    """
    n = len(dists)
    weighted_mean = [None] * n

    # Walk from root (index n-1) down to leaf (index 0)
    for i in range(n - 1, -1, -1):
        if dists[i] is None:
            weighted_mean[i] = None
        elif i == n - 1:
            weighted_mean[i] = float(dists[i])
        elif weighted_mean[i + 1] is None:
            weighted_mean[i] = None
        else:
            weighted_mean[i] = (dists[i] + weighted_mean[i + 1] * weighting) / (1 + weighting)

    results = []
    for i in range(n - 1, -1, -1):
        if dists[i] is None:
            ratio = None
        elif i == n - 1:
            ratio = 1
        elif weighted_mean[i + 1] is None:
            ratio = None
        else:
            ratio = dists[i] / weighted_mean[i]
        results.append((f"n{i}", None, ratio))
    return results


def test_weighting():
    """weighting param honoured"""
    dists = [random.randrange(10, 100) for _ in range(20)]
    tree_str = generate_tree(dists)

    assert do_prop_weighted_mean(tree_str) == expected_results(dists, weighting=0.8)
    assert do_prop_weighted_mean(tree_str, weighting=3) == expected_results(dists, weighting=3)
    assert expected_results(dists, 0.8) != expected_results(dists, 3)


def test_missing_branch_length(caplog):
    """Nodes with missing branch length get None weighted_mean and emit a warning.

    The recurrence depends on the parent's weighted_mean, so a missing branch
    length also poisons every descendant of that node.
    """
    dists = [random.randrange(10, 100) for _ in range(20)]
    dists[10] = None
    tree_str = generate_tree(dists)

    with caplog.at_level(logging.WARNING, logger="oz_tree_build.tree_build.tree_props.weighted_mean"):
        result = do_prop_weighted_mean(tree_str, weighting=3)

    # Preorder traversal visits n19..n0. n10 (at index 9) is missing, and the
    # cascade carries None down through n9..n0 (indices 10..19).
    assert [i for i, x in enumerate(result) if x[2] is None] == list(range(9, 20))
    assert any("n10" in r.message and r.levelno == logging.WARNING for r in caplog.records)
