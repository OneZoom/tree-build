import logging

logger = logging.getLogger(__name__)


def prop_weighted_mean(tree, weighting=0.8):
    """
    Given a ete4 (tree) object, add a "weighted_mean_ratio" property.

    Return name of property just added.
    """
    # Calculate weighted mean vs. ancestors
    for node in tree.traverse():
        if node.parent is None:
            node.props["weighted_mean"] = None if node.dist is None else float(node.dist)
            node.props["weighted_mean_ratio"] = None if node.dist is None else 1
        elif node.dist is None or node.parent.props["weighted_mean"] is None:
            if node.dist is None:
                logger.warning(f"Node {node.name} has no branch length")
            node.props["weighted_mean"] = None
            node.props["weighted_mean_ratio"] = None
        else:
            node.props["weighted_mean"] = (node.dist + (node.parent.props["weighted_mean"] * weighting)) / (
                1 + weighting
            )
            node.props["weighted_mean_ratio"] = node.dist / node.props["weighted_mean"]

    return "weighted_mean_ratio"
