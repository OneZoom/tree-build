"""
Tests for oz_tree_build.taxon_mapping_and_popularity.prop_array
"""

import struct

import dendropy
import pytest

from oz_tree_build.taxon_mapping_and_popularity.prop_array import prop_array


def build_tree(nwk, prop_name, prop_values, prop_format="u8"):
    """Parse (nwk), assigning node.<prop_name> = prop_values[node.label] where set."""
    t = dendropy.Tree.get(
        data=nwk,
        schema="newick",
        suppress_leaf_node_taxa=True,
        suppress_internal_node_taxa=True,
    )
    for node in t.preorder_node_iter():
        if node.label in prop_values:
            setattr(node, prop_name, prop_values[node.label])

    if not hasattr(t.seed_node, "prop_format"):
        t.seed_node.prop_format = {}
    t.seed_node.prop_format[prop_name] = prop_format

    return t


def read_packed(path, pack_format):
    sz = struct.calcsize("<" + pack_format)
    with open(path, "rb") as f:
        data = f.read()
    assert len(data) % sz == 0
    n = len(data) // sz
    return list(struct.unpack("<" + pack_format * n, data))


def test_prop_array_int_packing(tmp_path):
    """Integer properties pack as unsigned bytes; leaves and internals split into separate files in preorder."""
    t = build_tree(
        "((a,b)x,c)root;",
        "myprop",
        {"root": 5, "x": 12, "a": 1, "b": 2, "c": 3},
        prop_format="u8",
    )
    leaf_path, node_path = prop_array(str(tmp_path), t, "myprop")

    assert leaf_path == str(tmp_path / "myprop_leaves_u8.dat")
    assert node_path == str(tmp_path / "myprop_nodes_u8.dat")

    # Preorder: root, x, a, b, c -> leaves [a, b, c], internals [root, x]
    assert read_packed(leaf_path, "B") == [1, 2, 3]
    assert read_packed(node_path, "B") == [5, 12]


def test_prop_array_float_packing(tmp_path):
    """Float properties pack as 2-byte half-floats."""
    t = build_tree(
        "((a,b)x,c)root;",
        "myprop",
        {"root": 5.0, "x": 12.0, "a": 1.0, "b": 2.0, "c": 3.0},
        prop_format="f32",
    )
    leaf_path, node_path = prop_array(str(tmp_path), t, "myprop")

    assert leaf_path == str(tmp_path / "myprop_leaves_f32.dat")
    assert node_path == str(tmp_path / "myprop_nodes_f32.dat")

    assert struct.calcsize("<f") == 4
    assert read_packed(leaf_path, "f") == [1.0, 2.0, 3.0]
    assert read_packed(node_path, "f") == [5.0, 12.0]


def test_prop_array_preorder_matches_traversal(tmp_path):
    """Order of packed values follows preorder traversal of leaves / internals."""
    # Asymmetric tree to make ordering unambiguous
    t = build_tree(
        "(((a,b)x,c)y,(d,e)z)root;",
        "p",
        {"root": 100, "y": 50, "x": 25, "a": 1, "b": 2, "c": 3, "z": 75, "d": 4, "e": 5},
        prop_format="u8",
    )
    leaf_path, node_path = prop_array(str(tmp_path), t, "p")

    # Preorder visits: root, y, x, a, b, c, z, d, e
    assert read_packed(leaf_path, "B") == [1, 2, 3, 4, 5]
    assert read_packed(node_path, "B") == [100, 50, 25, 75]


def test_prop_array_unsupported_type_raises(tmp_path):
    """Non-numeric property type raises ValueError."""
    t = build_tree(
        "(a,b)root;",
        "myprop",
        {"root": "hello", "a": "x", "b": "y"},
        prop_format="z99",
    )
    with pytest.raises(ValueError, match="z99"):
        prop_array(str(tmp_path), t, "myprop")
