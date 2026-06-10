import re

from ..utilities.ete import node_get_ott

OT_INCLUSION_SYNTAX_RE = re.compile(r"(\w+)[_ ]ott(\d*)~?([-\d]*)@$")


def graft_tree(t, additional_trees, prefer_subtree_name=False, disable_recursion=False):
    """
    Resolve OneZoom inclusion syntax in ``t`` by grafting subtrees in place,
    replacing from ``additional_trees`` (a dict inclusion string -> tree).

    Walks ``t`` and, for every node whose name matches the inclusion syntax (a
    label ending in ``@``, see ``decypher_inclusion_syntax``).
    ``additional_trees`` is a dict of inclusion labels to ete4 trees.

    Naming of the grafted node:
      - default: use the name derived from the inclusion token (e.g. ``"Sub
        ott1"``), falling back to the subtree's root name if the token has no
        derived name
      - ``prefer_subtree_name=True``: use the subtree's root name, falling
        back to the token-derived name if the subtree root is unnamed

    By default, the function recurses into each grafted subtree so nested
    inclusions are also resolved. Pass ``disable_recursion=True`` to graft
    only one level, i.e. for OpenTree subtrees which won't contain inclusion syntax.

    Returns a list of inclusion labels that had no match in ``additional_trees``
    (including those found while recursing). Missing inclusions leave the
    placeholder node unchanged in ``t``.
    """
    missing_inclusions = []

    def is_leaf_fn(n):
        r = decypher_inclusion_syntax(n.name)
        if r is None:
            # No inclusion syntax, recurse
            return n.is_leaf

        if n.name not in additional_trees:
            # Not present, ignore for now
            missing_inclusions.append(n.name)
            return True

        # Graft sub_t at this point
        sub_t = additional_trees[n.name]
        if not disable_recursion:
            missing_inclusions.extend(graft_tree(sub_t, additional_trees, prefer_subtree_name))
        if prefer_subtree_name:
            n.name = sub_t.root.name or r["node_name"]
        else:
            n.name = r["node_name"] or sub_t.root.name
        if sub_t.root.dist is not None:
            n.dist = sub_t.root.dist
        for key, val in sub_t.root.props.items():
            if val is not None:
                n.props[key] = val
        n.children = sub_t.root.children

        # Replaced children, no point recursing through the old ones
        return True

    for _ in t.traverse(strategy="levelorder", is_leaf_fn=is_leaf_fn):
        # NB: We do all the work in the is_leaf_fn, so we can influence whether to recurse
        pass

    return missing_inclusions


def graft_extract_ot_subtrees(opentree_t, inclusions):
    """
    Extract the subtrees needed to satisfy a list of OneZoom inclusion labels
    from the full OpenTree tree.

    ``inclusions`` is a list of inclusion-syntax labels (e.g. ``"Sub_ott1@"``,
    ``"Renamed_ott~5@"``); each is parsed for its base OTT
    (see ``decypher_inclusion_syntax``). ``opentree_t`` is walked and any node
    whose OTT matches one of those base OTTs is detached and returned as a
    standalone subtree. ``opentree_t`` is mutated in place — every extracted
    subtree is removed from it.

    The extraction recurses into each detached subtree, so a requested OTT
    that lies inside another requested subtree is still extracted (and its
    outer subtree no longer contains it). The returned dict is keyed by the
    *original* inclusion label, preserving any rebase / exclusion syntax so
    callers can pass the result straight to ``graft_tree``.

    Inclusions whose base OTT does not appear in ``opentree_t`` are silently
    absent from the result.
    """
    # Organise inclusions by base_ott (as string)
    start_otts = {}
    for i in inclusions:
        r = decypher_inclusion_syntax(i)
        start_otts[str(r["base_ott"])] = r

    def prune_ot_subtrees(ot_t):
        out_trees = {}

        def is_leaf_fn(n):
            # No point checking leaves
            if n.is_leaf:
                return True

            # Does this node have a required OTT? If not, ignore it
            node_ott = node_get_ott(n)
            if node_ott is None or node_ott not in start_otts:
                return n.is_leaf
            r = start_otts[node_ott]
            del start_otts[node_ott]

            # Prune this tree, extract any required subtrees from this subtree
            sub_t = n.detach()
            out_trees.update(prune_ot_subtrees(sub_t))  # NB: node_ott now removed from start_otts, so won't loop
            out_trees[r["orig_name"]] = sub_t
            return True

        for _ in ot_t.traverse(strategy="preorder", is_leaf_fn=is_leaf_fn):
            # NB: We do all the work in the is_leaf_fn, so we can influence whether to recurse
            pass
        return out_trees

    return prune_ot_subtrees(opentree_t)


def present_in_tree(t, inclusion):
    """
    Is a node matching (inclusion) present anywhere in (t)?
    """
    r = decypher_inclusion_syntax(inclusion)
    to_find = "ott" + str(r["base_ott"])
    for n in t.traverse():
        if n.name.endswith(to_find):
            return n
    return None


def decypher_inclusion_syntax(node_name):
    """
    Parse inclusion syntax from node label
    Parse a single OneZoom token from label name
    """
    if not node_name or not node_name.endswith("@"):
        return None

    result = dict(
        orig_name=node_name,
    )

    match = OT_INCLUSION_SYNTAX_RE.match(node_name)
    if not match:
        # Has an @, but not ott syntax. Assume bespoke
        result["node_name"] = node_name[:-1]
        return result

    # split by minus signs
    result["excluded_otts"] = (match.group(3) or "").split("-")

    # If present, the first number after '=' is the tree to extract.
    first_number_after_equal = result["excluded_otts"].pop(0)
    result["base_ott"] = first_number_after_equal or match.group(2)

    # Note that we don't append the ott in the name if it came after the '='
    result["node_name"] = match.group(1)
    if not first_number_after_equal:
        result["node_name"] += f" ott{result['base_ott']}"
    return result


def remove_exclusions(t, exclusion_otts):
    """
    Given (t), prune any (exclusion_otts) from tree
    """
    orphan_ns = []

    def is_leaf_fn(n):
        node_ott = node_get_ott(n)
        if node_ott is None or node_ott not in exclusion_otts:
            return n.is_leaf

        orphan_ns.append(n.detach())
        return True

    if len(exclusion_otts) == 0:
        return orphan_ns
    exclusion_otts = set(str(x) for x in exclusion_otts)
    for _ in t.traverse(strategy="preorder", is_leaf_fn=is_leaf_fn):
        # NB: We do all the work in the is_leaf_fn, so we can influence whether to recurse
        pass
    return orphan_ns
