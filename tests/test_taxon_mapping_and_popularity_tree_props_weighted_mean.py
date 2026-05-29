import logging
import random

import dendropy

from oz_tree_build.taxon_mapping_and_popularity.tree_props.weighted_mean import prop_weighted_mean


def do_prop_weighted_mean(nwk, weighting=0.8):
    t = dendropy.Tree.get(
        data=nwk,
        schema="newick",
        suppress_leaf_node_taxa=True,
        suppress_internal_node_taxa=True,
    )
    assert prop_weighted_mean(t, weighting=weighting) == "weighted_mean_ratio"

    # Traverse tree, returning all periods
    return [(n.label, getattr(n, "date", None), n.weighted_mean_ratio) for n in t.preorder_node_iter()]


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

    assert do_prop_weighted_mean(tree_str) == expected_results(dists, weighting=0.8)
    assert do_prop_weighted_mean(tree_str, weighting=3) == expected_results(dists, weighting=3)
    assert expected_results(dists, 0.8) != expected_results(dists, 3)


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
        result = do_prop_weighted_mean(tree_str, weighting=3)

    assert result == expected_results(dists, weighting=3)
    # Preorder visits n19..n0. Only the root (index 0 → n19) and the missing
    # node (index 9 → n10) have ratio 0.0; descendants of n10 compute normally.
    assert [i for i, x in enumerate(result) if x[2] == 0.0] == [0, 9]
    assert any("n10" in r.message and r.levelno == logging.WARNING for r in caplog.records)
