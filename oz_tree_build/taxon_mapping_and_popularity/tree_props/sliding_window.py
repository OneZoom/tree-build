import logging
import math

logger = logging.getLogger(__name__)


def prop_sliding_window(tree, local_mean_width=5):
    """
    Given a DendroPy tree object, add "sliding_window" attribute to each node,
    representing the log-ratio between the node's edge length and the mean
    edge length of nearby ancestors (up to local_mean_width upwards) and
    descendants (up to local_mean_width deep).

    Return name of attribute just added.
    """
    for node in tree.preorder_node_iter():
        edge_length = node.edge.length
        if edge_length == 0:
            node.sliding_window = 0
            continue
        if edge_length is None or edge_length < 0:
            logger.warning(f"Node {node.label} has no / negative branch length {edge_length}")
            node.sliding_window = 0.0
            continue
        window_count = 0
        window_sum = 0

        # Work upwards, adding parents to window
        nn = node
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

        # Work downwards, adding descendents to window
        stack = [(c, 1) for c in node.child_node_iter()]
        while stack:
            dn, depth = stack.pop()
            dn_length = dn.edge.length
            if dn_length is None or dn_length < 0:
                logger.warning(f"Node {dn.label} has no / negative branch length {dn_length}")
                continue
            window_sum += dn_length
            window_count += 1
            if depth < local_mean_width:
                stack.extend((c, depth + 1) for c in dn.child_node_iter())

        if window_count == 0:
            node.sliding_window = 0.0
        else:
            node.sliding_window = math.log(edge_length / (window_sum / window_count))

    if not hasattr(tree.seed_node, "prop_format"):
        tree.seed_node.prop_format = {}
    tree.seed_node.prop_format["sliding_window"] = "f16"

    return "sliding_window"
