import logging

logger = logging.getLogger(__name__)


def prop_weighted_mean(tree, weighting=0.8):
    """
    Given a DendroPy tree object, add a "weighted_mean_ratio" attribute.

    Return name of attribute just added.
    """
    # Calculate weighted mean vs. ancestors
    for node in tree.preorder_node_iter():
        edge_length = node.edge.length
        parent = node.parent_node
        if parent is None:
            node.weighted_mean = 0.0
            node.weighted_mean_ratio = 0.0
        elif edge_length is None or parent.weighted_mean is None:
            if edge_length is None:
                logger.warning(f"Node {node.label} has no branch length")
            node.weighted_mean = 0.0
            node.weighted_mean_ratio = 0.0
        else:
            node.weighted_mean = (edge_length + (parent.weighted_mean * weighting)) / (1 + weighting)
            node.weighted_mean_ratio = edge_length / node.weighted_mean

    if not hasattr(tree.seed_node, "prop_format"):
        tree.seed_node.prop_format = {}
    tree.seed_node.prop_format["weighted_mean"] = "f16"
    tree.seed_node.prop_format["weighted_mean_ratio"] = "f16"

    return "weighted_mean_ratio"
