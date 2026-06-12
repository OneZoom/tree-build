import logging
import math

logger = logging.getLogger(__name__)


# Sourced from https://stratigraphy.org/supplementary#data
GEOLOGICAL_PERIODS = [
    {"period": "Unknown", "epoch": "Unknown", "mya_start": -1e9},
    {"period": "Quaternary", "epoch": "Holocene", "mya_start": 0.0117},
    {"period": "Quaternary", "epoch": "Pleistocene", "mya_start": 2.58},
    {"period": "Neogene", "epoch": "Pliocene", "mya_start": 5.333},
    {"period": "Neogene", "epoch": "Miocene", "mya_start": 23.04},
    {"period": "Paleogene", "epoch": "Oligocene", "mya_start": 33.9},
    {"period": "Paleogene", "epoch": "Eocene", "mya_start": 56},
    {"period": "Paleogene", "epoch": "Paleocene", "mya_start": 66},
    {"period": "Cretaceous", "epoch": "Upper", "mya_start": 100.5},
    {"period": "Cretaceous", "epoch": "Lower", "mya_start": 143.1},
    {"period": "Jurassic", "epoch": "Upper", "mya_start": 161.5},
    {"period": "Jurassic", "epoch": "Middle", "mya_start": 174.7},
    {"period": "Jurassic", "epoch": "Lower", "mya_start": 201.4},
    {"period": "Triassic", "epoch": "Upper", "mya_start": 237},
    {"period": "Triassic", "epoch": "Middle", "mya_start": 246.7},
    {"period": "Triassic", "epoch": "Lower", "mya_start": 251.902},
    {"period": "Permian", "epoch": "Lopingian", "mya_start": 259.51},
    {"period": "Permian", "epoch": "Guadalupian", "mya_start": 274.4},
    {"period": "Permian", "epoch": "Cisuralian", "mya_start": 298.9},
    {"period": "Carboniferous", "epoch": "Pennsylvanian", "mya_start": 323.4},
    {"period": "Carboniferous", "epoch": "Mississippian", "mya_start": 358.86},
    {"period": "Devonian", "epoch": "Upper", "mya_start": 382.31},
    {"period": "Devonian", "epoch": "Middle", "mya_start": 393.47},
    {"period": "Devonian", "epoch": "Lower", "mya_start": 419.62},
    {"period": "Silurian", "epoch": "Pridoli", "mya_start": 422.7},
    {"period": "Silurian", "epoch": "Ludlow", "mya_start": 426.7},
    {"period": "Silurian", "epoch": "Wenlock", "mya_start": 432.9},
    {"period": "Silurian", "epoch": "Llandovery", "mya_start": 443.1},
    {"period": "Ordovician", "epoch": "Upper", "mya_start": 458.2},
    {"period": "Ordovician", "epoch": "Middle", "mya_start": 471.3},
    {"period": "Ordovician", "epoch": "Lower", "mya_start": 486.85},
    {"period": "Cambrian", "epoch": "Furongian", "mya_start": 497},
    {"period": "Cambrian", "epoch": "Miaolingian", "mya_start": 506.5},
    {"period": "Cambrian", "epoch": "Series 2", "mya_start": 521},
    {"period": "Cambrian", "epoch": "Terreneuvian", "mya_start": 538.8},
    {"period": "Proterozoic", "epoch": "Neo-proterozoic", "mya_start": 1000},
    {"period": "Proterozoic", "epoch": "Meso-proterozoic", "mya_start": 1600},
    {"period": "Proterozoic", "epoch": "Paleo-proterozoic", "mya_start": 2500},
    {"period": "Archean", "epoch": "Neo-Archean", "mya_start": 2800},
    {"period": "Archean", "epoch": "Meso-Archean", "mya_start": 3200},
    {"period": "Archean", "epoch": "Paleo-Archean", "mya_start": 3600},
    {"period": "Archean", "epoch": "Eo-Archean", "mya_start": 4031},
    {"period": "Hadean", "epoch": "Hadean", "mya_start": 4567},
]


def prop_geological(tree):
    """
    Given an ete4 tree object, add a "geological" prop to each node,
    representing a 1-based period index.

    Assumes the tree already has an "age" prop representing an absolute age in Mya.

    Return name of prop just added.
    """
    # Turn array into (mya, idx) pairs
    lookup = [(p["mya_start"], idx) for idx, p in enumerate(GEOLOGICAL_PERIODS)]

    for node in tree.traverse("preorder"):
        n_age = node.props.get("age")
        if n_age is None:
            logger.warning(f"Node {node.name} has no age property")
            node.props["geological"] = 0
        else:
            for mya_start, idx in lookup:  # noqa: B007  # idx is used outside the lookup, not inside
                if n_age <= mya_start:
                    break
            else:
                # Fell off end
                idx = None
            node.props["geological"] = idx

    prop_format = tree.root.props.setdefault("prop_format", {})
    prop_format["geological"] = "u8"

    return "geological"


def prop_sliding_window(tree, local_mean_width=5):
    """
    Given an ete4 tree object, add a "sliding_window" prop to each node,
    representing the log-ratio between the node's edge length and the mean
    edge length of nearby ancestors (up to local_mean_width upwards) and
    descendants (up to local_mean_width deep).

    Return name of prop just added.
    """
    for node in tree.traverse("preorder"):
        edge_length = node.dist
        if edge_length == 0:
            node.props["sliding_window"] = 0
            continue
        if edge_length is None or edge_length < 0:
            logger.warning(f"Node {node.name} has no / negative branch length {edge_length}")
            node.props["sliding_window"] = 0.0
            continue
        window_count = 0
        window_sum = 0

        # Work upwards, adding parents to window
        nn = node
        for _ in range(local_mean_width):
            if nn.up is None:
                break
            nn_length = nn.dist
            if nn_length is None or nn_length < 0:
                logger.warning(f"Node {nn.name} has no / negative branch length {nn_length}")
                break
            window_sum += nn_length
            window_count += 1
            nn = nn.up

        # Work downwards, adding descendents to window
        stack = [(c, 1) for c in node.children]
        while stack:
            dn, depth = stack.pop()
            dn_length = dn.dist
            if dn_length is None or dn_length < 0:
                logger.warning(f"Node {dn.name} has no / negative branch length {dn_length}")
                continue
            window_sum += dn_length
            window_count += 1
            if depth < local_mean_width:
                stack.extend((c, depth + 1) for c in dn.children)

        if window_count == 0:
            node.props["sliding_window"] = 0.0
        else:
            node.props["sliding_window"] = math.log(edge_length / (window_sum / window_count))

    prop_format = tree.root.props.setdefault("prop_format", {})
    prop_format["sliding_window"] = "f16"

    return "sliding_window"


def prop_weighted_mean(tree, weighting=0.8):
    """
    Given an ete4 tree object, add a "weighted_mean_ratio" prop.

    Return name of prop just added.
    """
    # Calculate weighted mean vs. ancestors
    for node in tree.traverse("preorder"):
        edge_length = node.dist
        parent = node.up
        if parent is None:
            node.props["weighted_mean"] = 0.0
            node.props["weighted_mean_ratio"] = 0.0
        elif edge_length is None or parent.props.get("weighted_mean") is None:
            if edge_length is None:
                logger.warning(f"Node {node.name} has no branch length")
            node.props["weighted_mean"] = 0.0
            node.props["weighted_mean_ratio"] = 0.0
        else:
            node.props["weighted_mean"] = (edge_length + (parent.props["weighted_mean"] * weighting)) / (1 + weighting)
            node.props["weighted_mean_ratio"] = edge_length / node.props["weighted_mean"]

    prop_format = tree.root.props.setdefault("prop_format", {})
    prop_format["weighted_mean"] = "f16"
    prop_format["weighted_mean_ratio"] = "f16"

    return "weighted_mean_ratio"
