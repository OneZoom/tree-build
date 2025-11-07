"""
Tests for oz_tree_build.tree_build.build:apply_node_ages
"""

import ete4

from oz_tree_build.tree_build.build import NWK_PARSER, apply_node_ages


def do_apply_node_ages(nwk, node_ages):
    t = ete4.Tree(nwk, parser=NWK_PARSER)
    apply_node_ages(t, node_ages)

    out = {}
    for n in t.traverse():
        out[n.name] = n.props["date"]
    return out


def test_median_age():
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


def test_oz_inclusion():
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


def test_ott_matching():
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
