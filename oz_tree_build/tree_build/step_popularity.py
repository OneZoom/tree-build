import collections
import logging
from math import log

from ..utilities.ete import node_get_ott

logger = logging.getLogger(__name__)


def popularity_add_prop(
    tree,
    exclude_taxa=None,
):
    """
    Compute a phylogenetic popularity score for every node and store it on
    ``node.props["popularity"]`` (rounded to 2 dp).

    The raw per-node popularity is taken from ``node.props["taxon"]["raw_popularity"]``
    (see ``sum_popularity_over_tree``). Each node's score combines the raw popularity
    of its ancestors and descendants — so a node inherits some weight from its
    relatives, not just from its own ``raw_popularity``. See ``popularity_function``
    for the exact combination.

    ``exclude_taxa`` is forwarded to ``sum_popularity_over_tree`` and lets the
    caller zero out the raw popularity of named nodes before summation (e.g.
    excluding Dinosauria so its popularity is not credited to birds).

    A warning is logged for any Wikidata Qid that appears on more than one node,
    since that causes the same popularity to be counted twice.

    Must be run before monotomies / unary nodes are removed: those nodes often
    carry useful popularity that needs to percolate to their relatives first.
    Nodes synthesised by polytomy resolution are handled the same way as any
    other node.
    """
    sum_popularity_over_tree(tree, exclude_taxa=exclude_taxa)

    # now apply the popularity function
    Qids = set()
    for node in tree.traverse(strategy="preorder"):
        Q = node.props["taxon"].get("wikidata")
        if Q is not None:
            if Q in Qids:
                logger.warning(
                    f"duplicate wikidata Qids used (Q{Q}) - this will cause "
                    f"popularity double-counting for OTT {node_get_ott(node)}"
                )
            else:
                Qids.add(Q)
        pop = popularity_function(
            node.props["ancestors_popsum"],
            node.props["descendants_popsum"],
            node.props["n_ancestors"],
            node.props["n_descendants"],
        )

        # Round to 2 decimal places
        node.props["popularity"] = round(pop, 2)


def popularity_add_rank(tree):
    """
    Rank every leaf by its ``node.props["popularity"]`` and write the position
    to ``node.props["popularity_rank"]``. Rank 1 is the most popular leaf.

    Ties use standard competition ranking ("1224"): tied leaves share the lower
    rank and the next distinct value skips ahead by the size of the tie. For
    example, popularities [100, 50, 50, 50, 1] produce ranks [1, 2, 2, 2, 5].

    Internal nodes are neither ranked nor used as tie-breakers, and their
    ``popularity`` prop (if any) is ignored.

    Should be run after invalid tips and unary nodes have been removed, so the
    ranking reflects the final set of leaves.
    """
    leaf_popularities = collections.defaultdict(int)
    for node in tree.traverse():
        if node.is_leaf:
            leaf_popularities[node.props.get("popularity")] += 1
    cumsum = 1
    if None in leaf_popularities:
        return
    for k in sorted(leaf_popularities.keys(), reverse=True):
        add_next = leaf_popularities[k]
        leaf_popularities[k] = cumsum
        cumsum += add_next
    for node in tree.traverse():
        if node.is_leaf:
            node.props["popularity_rank"] = leaf_popularities[node.props.get("popularity")]


def popularity_function(
    sum_of_all_ancestor_popularities,
    sum_of_all_descendant_popularities,
    number_of_ancestors,
    number_of_descendants,
):
    """
    a) Dividing by number_of_ancestors+number_of_descendants would mean averaging
        popularity over all nodes, which would bias against taxa which have many
        unvisited/unpopular children
    b) Alternatively, dividing by a constant is equivalent to summing popularity over
        all nodes, which biases towards taxa with many fine taxonomic divisions
    We do something between the two by dividing by the log of the number of nodes.
    """
    if (
        (sum_of_all_ancestor_popularities is None)
        or (sum_of_all_descendant_popularities is None)
        or (number_of_ancestors is None)
        or (number_of_descendants is None)
    ):
        return None
    elif number_of_ancestors + number_of_descendants == 1:
        # Avoid a divide by zero error if this adds up to 1
        # Though the need for this makes me think that the log calculation
        # may not be mathematically sound
        return sum_of_all_ancestor_popularities + sum_of_all_descendant_popularities
    else:
        return (sum_of_all_ancestor_popularities + sum_of_all_descendant_popularities) / log(
            number_of_ancestors + number_of_descendants
        )


def popularity_add_info(
    tree,
    focal_labels,
):
    """
    Print debug info for ete4 nodes whose names appear in ``focal_labels``:
    each node's own popularity, its descendant popularity sum, a sample of
    its leaves, and the chain of ancestors with non-zero popularity.
    """
    remaining = set(focal_labels)
    for node in tree.traverse():
        if not remaining:
            break
        if node.name not in remaining:
            continue
        remaining.discard(node.name)
        print(
            "{}: own pop = {} (Q{}) descendant pop sum = {}".format(
                node.name,
                node.props["pop"],
                node.props["taxon"].get("wikidata", " absent"),
                node.props["descendants_popsum"],
            )
        )
        for t, tip in enumerate(node.leaves()):
            print(
                "Tip {} = {}: own_pop = {}, Qid = Q{}".format(
                    t,
                    tip.name,
                    tip.props.get("pop"),
                    tip.props["taxon"].get("wikidata", " absent"),
                )
            )
            if t > 100:
                print("More tips exist, but have been omitted")
                break
        ancestor = node.up
        while ancestor:
            if ancestor.props.get("pop"):
                print(f"Ancestors: {ancestor.name} = {ancestor.props['pop']:.2f}")
            ancestor = ancestor.up
    for missing in remaining:
        logger.warning(f"Problem reporting on focal taxon '{missing}': not found")


def sum_popularity_over_tree(tree, exclude_taxa=None):
    """
    Sum raw popularity values up and down an ete4 phylogenetic tree.

    Each node's raw popularity is taken from ``node.props["taxon"]["raw_popularity"]``
    It is copied onto ``node.props["pop"]`` and then summed across ancestors and
    descendants.

    We might want to exclude some names from the popularity metric (e.g. exclude
    archosaurs, to ensure birds don't gather popularity intended for dinosaurs).
    This is done by passing an array such as
    ``['Dinosauria_ott90215', 'Archosauria_ott335588']`` as the ``exclude_taxa`` argument
    -- the names are matched against ``node.name``.

    After running, the following props are set on every node:
        pop                        raw popularity for this node
        has_pop                    whether raw popularity was available
        descendants_popsum         popularity summed over all descendants
        n_descendants              number of descendants
        ancestors_popsum           popularity summed over all ancestors
        n_ancestors                number of ancestors
        n_pop_ancestors            number of ancestors with a popularity measure
    """
    exclude_taxa = set(exclude_taxa or [])

    logger.info("Tree read for phylogenetic popularity calc")

    # put popularity into the "pop" attribute
    for node in tree.traverse(strategy="preorder"):
        if node.name in exclude_taxa or node.props["taxon"].get("raw_popularity") is None:
            node.props["pop"] = 0
            node.props["has_pop"] = False
        else:
            node.props["pop"] = node.props["taxon"]["raw_popularity"]
            node.props["has_pop"] = True

    # go up the tree from the tips, summing up the popularity indices beneath and
    # adding the number of descendants
    for node in tree.traverse(strategy="postorder"):
        if node.is_leaf:
            node.props["descendants_popsum"] = 0
            node.props["n_descendants"] = 0
        parent = node.up
        if parent is None:
            continue
        parent.props["n_descendants"] = parent.props.get("n_descendants", 0) + 1 + node.props["n_descendants"]
        parent.props["descendants_popsum"] = (
            parent.props.get("descendants_popsum", 0) + node.props["pop"] + node.props["descendants_popsum"]
        )

    # go down the tree from the root, summing up the popularity indices above,
    # and summing up numbers of nodes
    for node in tree.traverse(strategy="preorder"):
        parent = node.up
        if parent is None:
            # this is the root.
            node.props["n_ancestors"] = 0
            node.props["n_pop_ancestors"] = 0
            node.props["ancestors_popsum"] = 0.0
        else:
            node.props["n_ancestors"] = parent.props["n_ancestors"] + 1
            node.props["ancestors_popsum"] = parent.props["ancestors_popsum"] + node.props["pop"]
            if node.props.get("has_pop"):
                node.props["n_pop_ancestors"] = parent.props["n_pop_ancestors"] + 1
            else:
                node.props["n_pop_ancestors"] = parent.props["n_pop_ancestors"]

    return tree
