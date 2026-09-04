import ete4

from oz_tree_build.tree_build.step_jsnewick import (
    jsnewick_brief_newick,
    jsnewick_cutpositionmap_binary,
    jsnewick_cutpositionmap_polytomy,
)
from oz_tree_build.tree_build.step_tidy import POLYTOMY_COMB, POLYTOMY_PROP


def _mark_polytomies(tree, *names):
    """Flag the named internal nodes as polytomy resolutions."""
    for node in tree.traverse():
        if node.name in names:
            node.props[POLYTOMY_PROP] = POLYTOMY_COMB


########################################
# jsnewick_brief_newick
########################################


def test_brief_newick_single_internal():
    """A single internal with two leaf children collapses to a bare ``()``."""
    t = ete4.Tree("(A,B);", parser=1)
    assert jsnewick_brief_newick(t) == "()"


def test_brief_newick_nested_left():
    """``((A,B),C)`` and ``(C,(A,B))`` both yield ``(())`` — leaves are invisible."""
    t = ete4.Tree("((A,B),C);", parser=1)
    assert jsnewick_brief_newick(t) == "(())"
    t = ete4.Tree("(C,(A,B));", parser=1)
    assert jsnewick_brief_newick(t) == "(())"


def test_brief_newick_two_subtrees():
    t = ete4.Tree("((A,B),(C,D));", parser=1)
    assert jsnewick_brief_newick(t) == "(()())"


def test_brief_newick_deep_caterpillar():
    t = ete4.Tree("(A,(B,(C,(D,E))));", parser=1)
    assert jsnewick_brief_newick(t) == "(((())))"


def test_brief_newick_polytomy_braces_default():
    """With the default polytomy_braces the polytomy prop is invisible."""
    t = ete4.Tree("((A:1,B:1)P:1,C:2);", parser=1)
    _mark_polytomies(t, "P")
    assert jsnewick_brief_newick(t) == "(())"


def test_brief_newick_polytomy_braces_overridden():
    """An internal with the polytomy prop gets the override braces; one without does not."""
    t = ete4.Tree("((A:1,B:1)P:1,C:2);", parser=1)
    _mark_polytomies(t, "P")
    assert jsnewick_brief_newick(t, polytomy_braces="{}") == "({})"

    t_unmarked = ete4.Tree("((A:1,B:1)P:1,C:2);", parser=1)
    assert jsnewick_brief_newick(t_unmarked, polytomy_braces="{}") == "(())"


def test_brief_newick_polytomy_ignores_zero_dist():
    """A zero-length branch is no longer a polytomy marker on its own."""
    t = ete4.Tree("((A:1,B:1)P:0,C:2);", parser=1)
    assert jsnewick_brief_newick(t, polytomy_braces="{}") == "(())"


def test_brief_newick_polytomy_root_excluded():
    """The root is never treated as a polytomy resolution, even if marked."""
    t = ete4.Tree("(A:1,B:1)R:1;", parser=1)
    _mark_polytomies(t, "R")
    assert jsnewick_brief_newick(t, polytomy_braces="{}") == "()"


def test_brief_newick_polytomy_braces_nested():
    """Multiple marked ancestors each get the polytomy braces."""
    t = ete4.Tree("(((A:1,B:1)P:1,C:2)Q:1,D:1);", parser=1)
    _mark_polytomies(t, "P", "Q")
    assert jsnewick_brief_newick(t, polytomy_braces="{}") == "({{}})"


########################################
# jsnewick_cutpositionmap_binary
########################################


def test_cutmap_binary_two_leaves_empty():
    """A single internal with two leaf children produces no entry — nothing to split."""
    t = ete4.Tree("(A,B);", parser=1)
    assert jsnewick_cutpositionmap_binary(t, threshold=0) == {}


def test_cutmap_binary_internal_then_leaf():
    """First child internal → cut is the position of that child's ``)``."""
    # brief = '(())': root open=0, inner open=1, inner close=2, root close=3.
    t = ete4.Tree("((A,B),C);", parser=1)
    assert jsnewick_cutpositionmap_binary(t, threshold=0) == {3: 2}


def test_cutmap_binary_leaf_then_internal():
    """First child leaf → cut is the parent's ``(`` position."""
    t = ete4.Tree("(C,(A,B));", parser=1)
    assert jsnewick_cutpositionmap_binary(t, threshold=0) == {3: 0}


def test_cutmap_binary_two_internals():
    """Both children internal → cut is the first child's ``)`` position."""
    # brief = '(()())': positions root=0/5, (A,B)=1/2, (C,D)=3/4.
    t = ete4.Tree("((A,B),(C,D));", parser=1)
    assert jsnewick_cutpositionmap_binary(t, threshold=0) == {5: 2}


def test_cutmap_binary_caterpillar():
    """Recursive descent records each non-trivial internal along the spine."""
    # (A,(B,(C,(D,E)))) → brief = '(((())))', root close at pos 7.
    t = ete4.Tree("(A,(B,(C,(D,E))));", parser=1)
    assert jsnewick_cutpositionmap_binary(t, threshold=0) == {7: 0, 6: 1, 5: 2}


def test_cutmap_binary_threshold_skips_small_subtrees():
    """Only subtrees whose bracket span exceeds the threshold get recursed into."""
    t = ete4.Tree("(A,(B,(C,(D,E))));", parser=1)
    # Subtree spans: root=8, (B,(C,(D,E)))=6, (C,(D,E))=4, (D,E)=2.
    # threshold=5 admits the first two; threshold=6 admits only the root.
    assert jsnewick_cutpositionmap_binary(t, threshold=5) == {7: 0, 6: 1}
    assert jsnewick_cutpositionmap_binary(t, threshold=6) == {7: 0}


########################################
# jsnewick_cutpositionmap_polytomy
########################################


def test_cutmap_polytomy_two_leaves_degenerate():
    """An internal with two leaf children falls back to the parent's own positions."""
    t = ete4.Tree("(A,B);", parser=1)
    # threshold=0 still enqueues the root (the worklist always seeds with it).
    assert jsnewick_cutpositionmap_polytomy(t, threshold=0) == {1: [0, 0, 1, 1]}


def test_cutmap_polytomy_internal_then_leaf():
    """Internal child gets its (start, end); trailing leaf gets the inverted
    [parent_close, parent_close-1] empty range."""
    t = ete4.Tree("((A,B),C);", parser=1)
    # Top-level root cut: c1=(A,B) spans [1,2], c2=C trails at [3,2].
    # Inner two-leaf node also gets degenerate entry at threshold=0.
    assert jsnewick_cutpositionmap_polytomy(t, threshold=0) == {
        3: [1, 2, 3, 2],
        2: [1, 1, 2, 2],
    }


def test_cutmap_polytomy_leaf_then_internal():
    """Leading leaf gets the inverted [parent_open+1, parent_open] empty range."""
    t = ete4.Tree("(C,(A,B));", parser=1)
    assert jsnewick_cutpositionmap_polytomy(t, threshold=0) == {
        3: [1, 0, 1, 2],
        2: [1, 1, 2, 2],
    }


def test_cutmap_polytomy_two_internals():
    """Both children internal → flat list of both children's spans."""
    t = ete4.Tree("((A,B),(C,D));", parser=1)
    assert jsnewick_cutpositionmap_polytomy(t, threshold=0) == {
        5: [1, 2, 3, 4],
        2: [1, 1, 2, 2],
        4: [3, 3, 4, 4],
    }


def test_cutmap_polytomy_threshold_off_by_one_vs_binary():
    """The polytomy recursion uses ``span > threshold`` (raw span), while binary
    uses ``span + 1 > threshold``; at the same threshold the polytomy map admits
    one fewer level than the binary map."""
    t = ete4.Tree("(A,(B,(C,(D,E))));", parser=1)
    # The (B,(C,(D,E))) child of root has bracket span 6-1 = 5.
    # Binary admits it (5+1 > 5); polytomy does not (5 > 5 is false), so only
    # the root entry survives in polytomy at threshold=5.
    assert jsnewick_cutpositionmap_binary(t, threshold=5) == {7: 0, 6: 1}
    assert jsnewick_cutpositionmap_polytomy(t, threshold=5) == {7: [1, 0, 1, 6]}

    # Dropping the threshold below the span lets polytomy recurse one more level.
    assert jsnewick_cutpositionmap_polytomy(t, threshold=3) == {
        7: [1, 0, 1, 6],
        6: [2, 1, 2, 5],
    }
