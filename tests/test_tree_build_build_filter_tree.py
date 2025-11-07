"""
Tests for oz_tree_build.tree_build.build:filter_tree
"""

import ete4

from oz_tree_build.tree_build.build import filter_tree


def do_filter_tree(nwk, excluded_otts):
    excluded_otts = [str(o) for o in excluded_otts]  # NB: Munge back to string so tests don't have to worry
    t = ete4.Tree(nwk, parser=1)
    filter_tree(t, excluded_otts)

    out = {}
    for n in t.traverse():
        out[n.name] = True
    return out


def test_filter_tree_nofilter():
    """No filter passed, nothing happens"""
    out = do_filter_tree(
        "(((a_ott1,b_ott2,c_ott3)d_ott4,(e_ott5)f_ott6)g_ott7,((h_ott8)i_ott9,j_ott10)k_ott11)l_ott12;", []
    )
    assert out == {
        "a_ott1": True,
        "b_ott2": True,
        "c_ott3": True,
        "d_ott4": True,
        "e_ott5": True,
        "f_ott6": True,
        "g_ott7": True,
        "h_ott8": True,
        "i_ott9": True,
        "j_ott10": True,
        "k_ott11": True,
        "l_ott12": True,
    }


def test_filter_tree_childrenpruned():
    """Proune node & children when excluded"""
    out = do_filter_tree(
        "(((a_ott1,b_ott2,c_ott3)d_ott4,(e_ott5)f_ott6)g_ott7,((h_ott8)i_ott9,j_ott10)k_ott11)l_ott12;", [6, 9, 10]
    )
    assert out == {
        "a_ott1": True,
        "b_ott2": True,
        "c_ott3": True,
        "d_ott4": True,
        "g_ott7": True,
        "k_ott11": True,
        "l_ott12": True,
    }
