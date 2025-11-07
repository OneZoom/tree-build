"""
Tests for oz_tree_build.tree_build.build:ages_from_dist
"""

import ete4

from oz_tree_build.tree_build.build import NWK_PARSER, ages_from_dist


def do_ages_from_dist(nwk):
    t = ete4.Tree(nwk, parser=NWK_PARSER)
    ages_from_dist(t)

    out = {}
    for n in t.traverse():
        out[n.name] = n.props["date"]
    return out


def test_oz_inclusion():
    """We should be OZ-inclusion aware when choosing leaf node ages"""
    out = do_ages_from_dist("(Paramastix_minuta,(Micrarchaeota_ott5248238@)mrcaott1234ott98321)biota_ott93302;")
    assert out == {
        # Despite being a leaf note, OZ-inclusion means this gets no age
        "Micrarchaeota_ott5248238@": None,
        # Genuine leaf node
        "Paramastix_minuta": 0,
        "biota_ott93302": None,
        "mrcaott1234ott98321": None,
    }


def test_propogation():
    """Propogates backwards using dist"""
    out = do_ages_from_dist("(((daisy:43,bessie:27)cows,(george:23,wilma:9)pigs)field,(cat)farmhouse)farmyard;")
    assert out == {
        # Leaves all get age 0
        "bessie": 0,
        "daisy": 0,
        "george": 0,
        "wilma": 0,
        "cat": 0,
        # Cows/pigs get maximum age
        "cows": max(43.0, 27.0),
        "pigs": max(23.0, 9.0),
        # Field gets no age, because cows/pigs entries don't
        "field": None,
        "farmhouse": None,
        "farmyard": None,
    }
