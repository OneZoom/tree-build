import os.path
import struct

from .tree_props.geological import prop_geological
from .tree_props.sliding_window import prop_sliding_window
from .tree_props.weighted_mean import prop_weighted_mean

PROP_FORMAT_TO_PACK = dict(
    c8="c",  # 8-bit chars
    i8="b",  # Signed 8-bit ints
    u8="B",  # Unsigned 8-bit ints
    f16="<e",  # LE 16-bit floats
    f32="<f",  # LE 32-bit floats
    f64="<d",  # LE 32-bit floats (doubles)
)


def prop_array(file_dir, tree, prop_name):
    """
    Given a DendroPy tree and prop_name, write out 2 packed arrays to file_dir:

        (prop_name)_leaves_(pack format).dat
        (prop_name)_nodes_(pack format).dat

    The ordering will match ordered_leaves/ordered_nodes
    """
    # Derive packing format from python type of property
    prop_format = getattr(tree.seed_node, "prop_format", {}).get(prop_name)
    if prop_format is None:
        raise ValueError(f"Property {prop_name} has no entry in prop_format. Has it been applied to the tree?")
    pack_format = PROP_FORMAT_TO_PACK.get(prop_format)
    if pack_format is None:
        raise ValueError(f"Unknown property format {prop_format}")

    leaf_path = os.path.join(file_dir, f"{prop_name}_leaves_{prop_format}.dat")
    node_path = os.path.join(file_dir, f"{prop_name}_nodes_{prop_format}.dat")
    with open(leaf_path, "wb") as leaf_f:
        with open(node_path, "wb") as node_f:
            # NB: Traverse behaviour has to match taxon_mapping_and_popularity.dendropy_extras.write_preorder_to_csv
            for node in tree.preorder_node_iter():
                value = getattr(node, prop_name)
                if node.is_leaf():
                    leaf_f.write(struct.pack(pack_format, value))
                else:
                    node_f.write(struct.pack(pack_format, value))
    return (leaf_path, node_path)


def prop_array_all(file_dir, tree):
    """
    Generate all known prop_arrays into (file_dir) from a DendroPy tree
    """
    out = []
    out.extend(prop_array(file_dir, tree, prop_geological(tree)))
    out.extend(prop_array(file_dir, tree, prop_sliding_window(tree)))
    out.extend(prop_array(file_dir, tree, prop_weighted_mean(tree)))
