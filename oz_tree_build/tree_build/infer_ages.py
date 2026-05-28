import logging
import re

from oz_tree_build.tree_build.oz_tokens import parse_one_zoom_token

logger = logging.getLogger(__name__)


def infer_ages(t, node_ages):
    """
    Modify supplied ete4 tree, filling in props["date"] on each node.

    Try inferring with branch length first, working backwards from leaves.

    If this to completely age tree, fill in any known nodes from node_ages.
    """
    ages_from_dist(t)
    if t.root.props["date"] is None:
        apply_node_ages(t, node_ages)


def apply_node_ages(t, node_ages):
    """
    Apply date properties from node_ages.json to the tree

    Based on tree_loading_oz_ete4:load_metadata by Jonathan Duke
    """

    def median_age(age_dicts, default):
        """Find median in list of [{"age": 123.45}, ..] dicts"""
        if len(age_dicts) == 0:
            return default

        ages = [float(x["age"]) for x in age_dicts]
        midpoint = int((len(ages) - 1) / 2)
        if len(ages) % 2 == 0:
            return (ages[midpoint] + ages[midpoint + 1]) / 2
        return ages[midpoint]

    extract_ott_re = re.compile(r"[_ ](ott\d+)$")

    if not node_ages:
        # No node ages, nothing to do
        return

    for n in t.traverse():
        if n.props.get("date") is not None:
            continue

        # Search for median age either by extracted OTT, or the full node string
        m = extract_ott_re.search(n.name or "")
        n.props["date"] = median_age(
            node_ages.get(m.group(1) if m else n.name, []),
            default=(0 if n.is_leaf and not parse_one_zoom_token(n.name) else None),
        )

        if n.props["date"] is not None and not n.is_leaf and n.props["date"] < 0.000001:
            logging.warning(f"Interior node {n.name} has median age of 0, setting to None")
            n.props["date"] = None


def ages_from_dist(t):
    """
    Apply date properties based on tree dist (branch length)

    Assume leaves have date 0, propogate rest based on dist.

    Based on tree_dating_oz_ete4:compute_dates
    """
    for n in t.traverse("postorder"):
        if n.is_leaf and parse_one_zoom_token(n.name):
            # Leaf node is an inclusion point, force this to have no date
            n.props["date"] = None
            continue

        parent_date = 0  # i.e. default given to leaf nodes

        for c in n.children:
            if c.props["date"] is None or c.dist is None:
                # Propogate missing branch lengths
                parent_date = None
                break
            new_date = c.props["date"] + c.dist
            if new_date > parent_date:
                parent_date = new_date

        n.props["date"] = parent_date
