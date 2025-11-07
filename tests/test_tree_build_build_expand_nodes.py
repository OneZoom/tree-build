"""
Tests for oz_tree_build.tree_build.build:expand_nodes
"""

import os
import unittest
import tempfile

import ete4

from oz_tree_build.tree_build.build import NWK_PARSER, expand_nodes


def do_expand_nodes(nwks, node_ages=[]):
    def node_to_dict(n):
        """Recursively turn a node into a dictionary of it's children"""
        if n.is_leaf:
            return None
        return {c.name: node_to_dict(c) for c in n.children}

    with tempfile.TemporaryDirectory(prefix="ut_expand_nodes") as tmp_path:
        # Write all newick files to temporary paths, make canned output for oz_token
        oz_token_vals = {}
        for nwk_name, nwk_dict in nwks.items():
            nwk_path = os.path.join(tmp_path, nwk_name + ".phy")
            with open(nwk_path, "w") as f:
                f.write(nwk_dict["content"])
            oz_token_vals[nwk_name + "@"] = dict(
                file=nwk_path,
                excluded_otts=nwk_dict.get("excluded_otts", []),
                base_ott=nwk_name if nwk_name.isdigit() else None,
                override_edge_length=nwk_dict.get("override_edge_length"),
                override_taxon=nwk_dict.get("override_taxon"),
                expand_nodes=True if nwk_name.isdigit() else False,
            )

        def mock_parse_one_zoom_token(node_label, parts_folders={}):
            out = oz_token_vals.get(node_label)
            if not out:
                return None
            out["node_name_in_parent"] = node_label.replace("@", "")
            return out

        with unittest.mock.patch("oz_tree_build.tree_build.build.parse_one_zoom_token", mock_parse_one_zoom_token):
            t = ete4.Tree(oz_token_vals["base@"]["file"], parser=NWK_PARSER)
            expand_nodes(t, {}, node_ages)
            return {t.root.name: node_to_dict(t.root)}


def test_prune_tree():
    """Prune all nodes below replacement point, and use subtree name over our nam"""
    out = do_expand_nodes(
        {
            "base": dict(content="(((daisy:43,bessie:27)cows@,(george:23,wilma:9)pigs)field,(cat)farmhouse)farmyard;"),
            "cows": dict(content="(moo,mooo,moooo);"),
        }
    )
    assert out == {
        "farmyard": {
            "farmhouse": {"cat": None},
            "field": {"cows": {"moo": None, "mooo": None, "moooo": None}, "pigs": {"george": None, "wilma": None}},
        }
    }


def test_substitute_name_ott():
    """For ott substitutions, use subtree name over our own"""
    out = do_expand_nodes(
        {
            "base": dict(content="(((daisy:43,bessie:27)1234@,(george:23,wilma:9)pigs)field,(cat)farmhouse)farmyard;"),
            "1234": dict(content="(moo,mooo,moooo1);"),
        }
    )
    # NB: @ stripped, i.e. we used node_name_in_parent
    assert out == {
        "farmyard": {
            "farmhouse": {"cat": None},
            "field": {"1234": {"moo": None, "mooo": None, "moooo1": None}, "pigs": {"george": None, "wilma": None}},
        }
    }
    out = do_expand_nodes(
        {
            "base": dict(content="(((daisy:43,bessie:27)1234@,(george:23,wilma:9)pigs)field,(cat)farmhouse)farmyard;"),
            "1234": dict(content="(moo,mooo,moooo2)cows;"),
        }
    )
    assert out == {
        "farmyard": {
            "farmhouse": {"cat": None},
            "field": {"cows": {"moo": None, "mooo": None, "moooo2": None}, "pigs": {"george": None, "wilma": None}},
        }
    }
    out = do_expand_nodes(
        {
            "base": dict(content="(((daisy:43,bessie:27)1234@,(george:23,wilma:9)pigs)field,(cat)farmhouse)farmyard;"),
            "1234": dict(content="(moo,mooo,moooo3);", override_taxon="cowscowscows"),
        }
    )
    assert out == {
        "farmyard": {
            "farmhouse": {"cat": None},
            "field": {
                "cowscowscows": {"moo": None, "mooo": None, "moooo3": None},
                "pigs": {"george": None, "wilma": None},
            },
        }
    }


def test_substitute_name_bespoke():
    """For bespoke, use parent's name over subtree"""
    out = do_expand_nodes(
        {
            "base": dict(content="(((daisy:43,bessie:27)1234,(george:23,wilma:9)pigs)field,(cat@)farmhouse)farmyard;"),
            "cat": dict(content="(kitten1,kitten2,kitten3)puss;"),
        }
    )
    assert out == {
        "farmyard": {
            "farmhouse": {"cat": {"kitten1": None, "kitten2": None, "kitten3": None}},
            "field": {"1234": {"bessie": None, "daisy": None}, "pigs": {"george": None, "wilma": None}},
        }
    }
