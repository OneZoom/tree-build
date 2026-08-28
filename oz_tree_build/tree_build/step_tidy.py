# Prop marking a node as an artificial split inserted to break up a polytomy.
# Its value says *how* the topology was chosen, since the two stages that
# resolve polytomies do so very differently. Any node carrying the prop is
# artificial, so consumers that only care about that can test it for truth.
POLYTOMY_PROP = "polytomy"

# ete4's resolve_polytomy: deterministic, and not a sample of anything -- it
# pairs children off in whatever order they happen to be in, so a polytomy of
# n children always becomes the same left-nested comb.
POLYTOMY_COMB = "comb"

# dated_complete_tree.tree_fixing.fix_polytomy: draws uniformly at random from
# the possible topologies, using a seeded rng.
POLYTOMY_RANDOM = "random"

# Name fix_polytomy gives the nodes it inserts, and the only trace of them that
# survives into the newick date_tree writes out
OT_POLYTOMY_NAME = "mrcapoly"


def tidy_resolve_polytomies(tree, kind=POLYTOMY_COMB):
    """
    Resolve any polytomies in ``tree`` via ete4's ``resolve_polytomy``, marking
    each artificially inserted node with ``POLYTOMY_PROP`` set to ``kind``.

    ``resolve_polytomy`` leaves inserted nodes with ``dist == 0``, but branch
    lengths are regenerated from dates later in the pipeline, so the resolution
    has to be recorded as a prop to survive that.

    Return number of nodes inserted.
    """
    pre_existing = {id(n) for n in tree.traverse()}
    tree.resolve_polytomy()

    count = 0
    for node in tree.traverse():
        if id(node) not in pre_existing:
            node.props[POLYTOMY_PROP] = kind
            count += 1
    return count


def tidy_mark_resolved_polytomies(tree, kind=POLYTOMY_RANDOM, name=OT_POLYTOMY_NAME):
    """
    Mark nodes in an already-resolved ``tree`` with ``POLYTOMY_PROP`` set to
    ``kind``, so they match those ``tidy_resolve_polytomies`` marks itself.

    OpenTree subtrees arrive polytomy-resolved by
    ``dated_complete_tree.tree_fixing.fix_polytomy``, which identifies the nodes
    it inserts by giving them the name ``mrcapoly``. That name is all we have to
    go on: ``date_tree.nwk_write`` emits only the ``date`` prop, and the tree is
    written before ``compute_branch_lengths`` runs, so the nodes arrive with no
    branch length either.

    Return number of nodes marked.
    """
    count = 0
    for node in tree.traverse():
        if node.name == name:
            node.props[POLYTOMY_PROP] = kind
            count += 1
    return count


def tidy_infill_dates_bottomup(tree):
    """
    Working bottom-upwards, fill in missing date properties based on branch lengths.
    """
    for node in tree.traverse(strategy="postorder"):
        if node.is_leaf:
            node.props["date"] = 0
        else:
            for c in node.children:
                if c.props.get("date") is not None and c.dist is not None:
                    c_date = c.props["date"] + c.dist
                    if node.props.get("date") is None or node.props["date"] < c_date:
                        node.props["date"] = c_date


def tidy_clear_conflicting_dates_topdown(parent, mrad=None):
    """
    Work through tree, removing dates older than their most recent ancestor.
    """
    if parent.props.get("date") is not None:
        if mrad is not None and (parent.props["date"] - mrad) > 1e-5:
            # date is greater than mrad, this shouldn't happen
            parent.props["date"] = None
        else:
            mrad = parent.props["date"]
    for c in parent.children:
        tidy_clear_conflicting_dates_topdown(c, mrad)
