"""
Tests for oz_tree_build.infer_ages
"""

import ete4

from oz_tree_build.tree_build.build_oz_tree import NWK_READ_PARSER
from oz_tree_build.tree_build.infer_ages import ages_from_dist, apply_node_ages, infer_ages


def do_apply_node_ages(nwk, node_ages):
    t = ete4.Tree(nwk, parser=NWK_READ_PARSER)
    apply_node_ages(t, node_ages)

    out = {}
    for n in t.traverse():
        out[n.name] = n.props["date"]
    return out


def do_infer_ages(nwk, node_ages):
    t = ete4.Tree(nwk, parser=NWK_READ_PARSER)
    infer_ages(t, node_ages)

    out = {}
    for n in t.traverse():
        out[n.name] = n.props["date"]
    return out


def do_ages_from_dist(nwk):
    t = ete4.Tree(nwk, parser=NWK_READ_PARSER)
    ages_from_dist(t)

    out = {}
    for n in t.traverse():
        out[n.name] = n.props["date"]
    return out


def test_apply_node_ages_median_age():
    """Make sure we set an appropriate median"""

    def tma(ages, expected):
        out = do_apply_node_ages(
            "(notme)targetnode;",
            dict(
                targetnode=[dict(age=str(a)) for a in ages],
            ),
        )
        assert out == dict(
            targetnode=expected,
            notme=0,
        )

    tma([], None)
    tma([4], 4)
    tma([1, 2, 3], 2)
    tma([1, 5, 8, 10], (5 + 8) / 2)


def test_apply_node_ages_oz_inclusion():
    """We should be OZ-inclusion aware when choosing leaf node ages"""
    out = do_apply_node_ages(
        "(Paramastix_minuta,(Micrarchaeota_ott5248238@)mrcaott1234ott98321)biota_ott93302;", dict(no=[dict(age=4)])
    )
    assert out == {
        # None: internal node
        "mrcaott1234ott98321": None,
        # None: OZ inclusion node
        "Micrarchaeota_ott5248238@": None,
        # 0: Genuine node
        "Paramastix_minuta": 0,
        # None: internal node
        "biota_ott93302": None,
    }


def test_apply_node_ages_ott_matching():
    """We should match OTTs where present"""
    out = do_apply_node_ages(
        "(Paramastix_minuta ott19182,(Micrarchaeota_ott5248238@)mrcaott1234ott98321)biota_ott93302;",
        dict(
            ott5248238=[dict(age=5248238.0)],
            ott19182=[dict(age=19182.0)],
            mrcaott1234ott98321=[dict(age=98321.0)],
            ott93302=[dict(age=93302.0)],
        ),
    )
    assert out == {
        # Not assigened to OZ inclusion node
        "Micrarchaeota_ott5248238@": None,
        # Matched OTT substring
        "Paramastix_minuta ott19182": 19182.0,
        # Matched OTT substring
        "biota_ott93302": 93302.0,
        # Matched exact name
        "mrcaott1234ott98321": 98321.0,
    }


def test_ages_from_dist_oz_inclusion():
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


def test_infer_ages_dist_succeeds_ignores_node_ages():
    """When dist fully dates the tree, node_ages is not applied"""
    out = do_infer_ages(
        "(daisy:43,bessie:27)cows;",
        dict(cows=[dict(age=999)]),  # Would produce 999 if applied
    )
    assert out == {
        "daisy": 0,
        "bessie": 0,
        "cows": 43.0,  # From dist, not node_ages
    }


def test_infer_ages_falls_back_to_node_ages():
    """When dist leaves root undated, node_ages fills in the gaps"""
    out = do_infer_ages(
        "(daisy,bessie)cows;",
        dict(cows=[dict(age=50)]),
    )
    assert out == {
        "daisy": 0,
        "bessie": 0,
        "cows": 50,
    }


def test_infer_ages_node_ages_preserves_dist_leaves():
    """Leaves dated by dist (age 0) are not overwritten when node_ages runs"""
    out = do_infer_ages(
        "(daisy,bessie)cows;",
        dict(
            cows=[dict(age=50)],
            daisy=[dict(age=999)],  # Would replace leaf if dist date not preserved
        ),
    )
    assert out == {
        "daisy": 0,  # Dist set this; node_ages must not overwrite it
        "bessie": 0,
        "cows": 50,
    }


def test_ages_from_dist_propogation():
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
