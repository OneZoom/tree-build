import json
import random

import ete4

from oz_tree_build.tree_build.step_jsnewick import (
    jsnewick_brief_newick,
    jsnewick_cutpositionmap_binary,
    jsnewick_cutpositionmap_polytomy,
)
from oz_tree_build.utilities import make_js_treefiles

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
    """With the default polytomy_braces the dist=0 marker is invisible."""
    t = ete4.Tree("((A:1,B:1):0,C:2);", parser=1)
    assert jsnewick_brief_newick(t) == "(())"


def test_brief_newick_polytomy_braces_overridden():
    """An internal with dist=0 gets the override braces; non-zero dist does not."""
    t = ete4.Tree("((A:1,B:1):0,C:2);", parser=1)
    assert jsnewick_brief_newick(t, polytomy_braces="{}") == "({})"

    t_nonzero = ete4.Tree("((A:1,B:1):3,C:2);", parser=1)
    assert jsnewick_brief_newick(t_nonzero, polytomy_braces="{}") == "(())"


def test_brief_newick_polytomy_root_excluded():
    """The root's own dist is ignored even when set to 0."""
    t = ete4.Tree("(A:1,B:1):0;", parser=1)
    assert jsnewick_brief_newick(t, polytomy_braces="{}") == "()"


def test_brief_newick_polytomy_braces_nested():
    """Multiple dist=0 ancestors each get the polytomy braces."""
    t = ete4.Tree("(((A:1,B:1):0,C:2):0,D:1);", parser=1)
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


def test_cutmap_binary_matches_legacy_on_ladderized_tree():
    """On a tree ladderized smallest-subtree-first, the new map matches the legacy
    string-based generator byte-for-byte. The legacy algorithm assumes leaf-first
    child ordering — ladderize(ascending=True) is what the OZ pipeline runs to
    enforce that."""
    random.seed(1234)
    nwk = _random_binary_newick(25)
    t = ete4.Tree(nwk, parser=1)
    t.ladderize()  # ete4 ladderize is ascending by default

    brief = jsnewick_brief_newick(t)
    new_map = jsnewick_cutpositionmap_binary(t, threshold=0)
    assert new_map == _legacy_binary_map(brief, 0)


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


def test_cutmap_polytomy_matches_legacy_on_ladderized_tree():
    """Matches the legacy polytomy generator on a leaf-first-ordered tree."""
    random.seed(5678)
    nwk = _random_binary_newick(25)
    t = ete4.Tree(nwk, parser=1)
    t.ladderize()

    brief = jsnewick_brief_newick(t)
    new_map = jsnewick_cutpositionmap_polytomy(t, threshold=0)
    assert new_map == _legacy_polytomy_map(brief, 0)


########################################
# helpers
########################################


def _random_binary_newick(n_leaves):
    """Generate a random binary newick string with ``n_leaves`` leaves."""

    def rec(i, j):
        if j - i == 1:
            return f"L{i}"
        m = random.randint(i + 1, j - 1)
        return f"({rec(i, m)},{rec(m, j)})"

    return rec(0, n_leaves) + ";"


def _legacy_binary_map(brief, threshold):
    """Run the legacy generator and parse the embedded JSON back into a dict."""
    js = make_js_treefiles.generate_binary_cut_position_map(brief, threshold)
    payload = js.split("'", 2)[1]
    return {int(k): v for k, v in json.loads(payload).items()}


def _legacy_polytomy_map(brief, threshold):
    js = make_js_treefiles.generate_polytomy_cut_position_map(brief, threshold)
    payload = js.split("'", 2)[1]
    return {int(k): v for k, v in json.loads(payload).items()}
