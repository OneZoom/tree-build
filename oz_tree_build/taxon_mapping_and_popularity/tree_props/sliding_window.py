import logging
import math

logger = logging.getLogger(__name__)


def prop_sliding_window(tree, local_mean_width=5):
    """
    Given a DendroPy tree object, add "sliding_window" attribute to each node,
    representing a moving average of width (local_mean_width) upwards.

    Return name of attribute just added.
    """
    for node in tree.preorder_node_iter():
        edge_length = node.edge.length
        if edge_length == 0:
            node.sliding_window = 0
            continue

        nn = node
        window_count = 0
        window_sum = 0
        for _ in range(local_mean_width):
            if nn.parent_node is None:
                break
            nn_length = nn.edge.length
            if nn_length is None or nn_length < 0:
                logger.warning(f"Node {nn.label} has no / negative branch length {nn_length}")
                break
            window_sum += nn_length
            window_count += 1
            nn = nn.parent_node

        if window_count == 0:
            node.sliding_window = 0.0
        else:
            node.sliding_window = math.log(edge_length / (window_sum / window_count))

    if not hasattr(tree.seed_node, "prop_format"):
        tree.seed_node.prop_format = {}
    tree.seed_node.prop_format["sliding_window"] = "f16"

    return "sliding_window"
