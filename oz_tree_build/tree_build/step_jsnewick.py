"""
Tree-to-string converters used by the JS frontend.

OneZoom's frontend slurps a "bracket-only" newick that has had every
leaf name, branch length, comma, and semicolon stripped — only ``(``
and ``)`` characters remain. Internal nodes are identified by their
character position in that string, and a cut-position map tells the
frontend where to split each internal node's two children.

Historically these strings were built by reading a named-leaf newick
back off disk and string-munging it (see
``oz_tree_build.utilities.make_js_treefiles.tidy_newick`` and
``generate_binary_cut_position_map``). This module produces the same
output directly from an ete4 tree, with no on-disk round-trip.
"""


def jsnewick_brief_newick(tree, polytomy_braces="()"):
    """
    Return the bracket-only string for ``tree``.

    Equivalent to writing the tree as newick, dropping leaf names and
    branch lengths, then stripping commas, semicolons, and newlines:
    each internal node contributes a matching ``(`` and ``)``, leaves
    contribute nothing. The ete4 tree built from ``((A,B),C);`` yields
    ``"(())"``.

    ``polytomy_braces`` is a two-character string overriding the
    brackets used for any *non-root* internal whose ``dist == 0`` —
    the marker ``resolve_polytomy`` leaves on an artificial split.
    Pass e.g. ``"{}"`` to flag those nodes for the frontend.
    """
    parts = []
    for node, action in _walk_internal(tree):
        braces = polytomy_braces if (node.up is not None and node.dist == 0) else "()"
        parts.append(braces[0] if action == "open" else braces[1])
    return "".join(parts)


def jsnewick_cutpositionmap_binary(tree, threshold=10000):
    """
    Cut-position map for an ete4 ``tree``.

    Keys are the tidy-string position of an internal node's ``)``;
    the value is the position of the last character of that node's
    first child — i.e. where the frontend should split the subtree
    string into its two children. An internal whose first child is a
    leaf records the parent's ``(`` position as the cut (the leaf
    occupies an empty range immediately after).

    Only the root and any internal node whose own subtree contributes
    more than ``threshold`` characters to the tidied string get an
    entry; the recursion mirrors ``make_js_treefiles`` exactly. An
    internal with two leaf children produces no entry (there is no
    further split for the frontend to make).

    The tree is assumed to be binary; nodes with fewer than two
    children are skipped and any third-or-later child of a polytomy
    is ignored — callers should resolve polytomies first.

    Equivalent to ``make_js_treefiles.generate_binary_cut_position_map``
    """
    start_pos = {}
    end_pos = {}
    for pos, (node, action) in enumerate(_walk_internal(tree)):
        if action == "open":
            start_pos[id(node)] = pos
        else:
            end_pos[id(node)] = pos

    cut_map = {}
    worklist = [tree]
    while worklist:
        node = worklist.pop(0)
        children = list(node.children)
        if len(children) < 2:
            continue
        c1, c2 = children[0], children[1]

        if c1.is_leaf and c2.is_leaf:
            continue

        cut = start_pos[id(node)] if c1.is_leaf else end_pos[id(c1)]
        cut_map[end_pos[id(node)]] = cut

        for child in (c1, c2):
            if child.is_leaf:
                continue
            if end_pos[id(child)] - start_pos[id(child)] + 1 > threshold:
                worklist.append(child)

    return cut_map


def jsnewick_cutpositionmap_polytomy(tree, threshold=10000):
    """
    Cut-position map for an ete4 ``tree``.

    Keys are the tidy-string position of an internal node's ``)``;
    the value is a flat ``[start1, end1, start2, end2]`` list describing
    each of the node's two children:
      - An internal child contributes its bracket range ``(start, end)``.
      - A leaf child contributes an inverted range marking the empty
        position the leaf occupies between siblings (``start > end``).
      - An internal whose children are *both* leaves falls back to the
        degenerate ``[start, start, end, end]`` form — using the
        parent's own bracket positions — matching the original
        algorithm's cut-point-not-found case.

    Only the root and any internal node whose own subtree contributes
    more than ``threshold + 1`` characters to the tidied string get an
    entry; the (off-by-one) threshold check mirrors
    ``make_js_treefiles`` exactly.

    The tree is assumed to be binary; nodes with fewer than two
    children are skipped and any third-or-later child of a polytomy
    is ignored — callers should resolve polytomies first.

    Equivalent to ``make_js_treefiles.generate_polytomy_cut_position_map``
    """
    start_pos = {}
    end_pos = {}
    for pos, (node, action) in enumerate(_walk_internal(tree)):
        if action == "open":
            start_pos[id(node)] = pos
        else:
            end_pos[id(node)] = pos

    cut_map = {}
    worklist = [tree]
    while worklist:
        node = worklist.pop(0)
        children = list(node.children)
        if len(children) < 2:
            continue
        c1, c2 = children[0], children[1]
        s_n = start_pos[id(node)]
        e_n = end_pos[id(node)]

        if c1.is_leaf and c2.is_leaf:
            cut_map[e_n] = [s_n, s_n, e_n, e_n]
        else:
            pair1 = [s_n + 1, s_n] if c1.is_leaf else [start_pos[id(c1)], end_pos[id(c1)]]
            pair2 = [e_n, e_n - 1] if c2.is_leaf else [start_pos[id(c2)], end_pos[id(c2)]]
            cut_map[e_n] = pair1 + pair2

        for child in (c1, c2):
            if child.is_leaf:
                continue
            if end_pos[id(child)] - start_pos[id(child)] > threshold:
                worklist.append(child)

    return cut_map


def _walk_internal(tree):
    """
    Iterative DFS yielding ``(node, action)`` for every internal node
    in the order tidy_newick would emit them. ``action`` is ``"open"``
    on first visit and ``"close"`` on return. Leaves contribute no
    character to the tidied string and are skipped.
    """
    stack = [(tree, False)]
    while stack:
        node, visited = stack.pop()
        if node.is_leaf:
            continue
        if visited:
            yield node, "close"
        else:
            yield node, "open"
            stack.append((node, True))
            for child in reversed(list(node.children)):
                stack.append((child, False))
