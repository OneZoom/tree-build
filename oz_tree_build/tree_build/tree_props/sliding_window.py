import logging
import math

logger = logging.getLogger(__name__)


def prop_sliding_window(tree, local_mean_width=5):
    """
    Given an ete4 tree object, add "sliding_window" property to each node,
    representing a moving average of width (local_mean_width) upwards.

    Return name of property just added.
    """
    for node in tree.traverse():
        nn = node
        window_count = 0
        window_sum = 0
        for _ in range(local_mean_width):
            if nn.dist is None or nn.dist < 0:
                logger.warning(f"Node {nn.name} has no / negative branch length {nn.dist}")
                break
            window_sum += nn.dist
            window_count += 1
            if not nn.parent:
                break
            nn = nn.parent

        node.props["sliding_window"] = None if window_count == 0 else math.log(node.dist / (window_sum / window_count))
    return "sliding_window"
