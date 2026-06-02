import csv
import os
import struct

import ete4
import pytest

from oz_tree_build.tree_build.step_output import (
    output_add_prop_ids,
    output_mysqlexport,
    output_proparray,
)


def _by_name(tree):
    return {n.name: n for n in tree.traverse()}


def _prep(tree, taxon_overrides=None):
    """
    Give every node the minimum props output_mysqlexport requires:
    a (possibly empty) taxon dict and the id props from output_add_prop_ids.
    `taxon_overrides` is `{node_name: {key: value, ...}}`.
    """
    taxon_overrides = taxon_overrides or {}
    for n in tree.traverse():
        n.props["taxon"] = dict(taxon_overrides.get(n.name, {}))
    output_add_prop_ids(tree)


def _read_csv(out_dir, name):
    with open(os.path.join(out_dir, name), encoding="utf-8") as f:
        return list(csv.reader(f))


class TestOutputAddPropIds:
    def test_minimal_two_leaf_tree(self):
        # Single internal node with two leaves. The root is the only node
        # that receives id/leaf_lft/leaf_rgt/node_rgt.
        t = ete4.Tree("(A,B)R;", parser=1)
        output_add_prop_ids(t)
        assert t.props["id"] == 1
        assert t.props["leaf_lft"] == 1
        assert t.props["leaf_rgt"] == 2
        # No internal node sits below the root, so its rightmost-internal
        # descendant is itself.
        assert t.props["node_rgt"] == 1

    def test_leaves_get_no_id_props(self):
        # Leaves are implicitly numbered by their preorder position; the
        # function must not write any of the id props onto leaf nodes.
        t = ete4.Tree("((A,B)I,(C,D)J)R;", parser=1)
        output_add_prop_ids(t)
        for leaf in t.leaves():
            assert "id" not in leaf.props
            assert "leaf_lft" not in leaf.props
            assert "leaf_rgt" not in leaf.props
            assert "node_rgt" not in leaf.props

    def test_internal_ids_are_one_based_preorder(self):
        # Internal nodes receive ids 1..N in preorder.
        t = ete4.Tree("((A,B)I,(C,(D,E)J)K)R;", parser=1)
        output_add_prop_ids(t)
        ids = [n.props["id"] for n in t.traverse("preorder") if not n.is_leaf]
        assert ids == [1, 2, 3, 4]
        nodes = _by_name(t)
        assert nodes["R"].props["id"] == 1
        assert nodes["I"].props["id"] == 2
        assert nodes["K"].props["id"] == 3
        assert nodes["J"].props["id"] == 4

    def test_leaf_lft_is_position_of_leftmost_descendant_leaf(self):
        # leaf_lft is the 1-based preorder position of the subtree's
        # leftmost leaf.
        t = ete4.Tree("((A,B)I,(C,(D,E)J)K)R;", parser=1)
        output_add_prop_ids(t)
        nodes = _by_name(t)
        # Preorder leaf order is A, B, C, D, E → positions 1..5.
        assert nodes["R"].props["leaf_lft"] == 1  # leftmost descendant is A
        assert nodes["I"].props["leaf_lft"] == 1  # leftmost descendant is A
        assert nodes["K"].props["leaf_lft"] == 3  # leftmost descendant is C
        assert nodes["J"].props["leaf_lft"] == 4  # leftmost descendant is D

    def test_leaf_rgt_is_position_of_rightmost_descendant_leaf(self):
        # leaf_rgt is the 1-based preorder position of the subtree's
        # rightmost leaf.
        t = ete4.Tree("((A,B)I,(C,(D,E)J)K)R;", parser=1)
        output_add_prop_ids(t)
        nodes = _by_name(t)
        assert nodes["R"].props["leaf_rgt"] == 5  # rightmost descendant is E
        assert nodes["I"].props["leaf_rgt"] == 2  # rightmost descendant is B
        assert nodes["K"].props["leaf_rgt"] == 5  # rightmost descendant is E
        assert nodes["J"].props["leaf_rgt"] == 5  # rightmost descendant is E

    def test_node_rgt_for_terminal_internal_is_self(self):
        # If every child of an internal node is a leaf, its rightmost
        # internal descendant is itself.
        t = ete4.Tree("((A,B)I,(C,D)J)R;", parser=1)
        output_add_prop_ids(t)
        nodes = _by_name(t)
        assert nodes["I"].props["node_rgt"] == nodes["I"].props["id"]
        assert nodes["J"].props["node_rgt"] == nodes["J"].props["id"]

    def test_node_rgt_walks_rightmost_internal_descendant(self):
        # For a non-terminal internal node, node_rgt is the id of the
        # rightmost internal descendant (assuming ascending ladderization
        # so the rightmost child holds the biggest subtree).
        t = ete4.Tree("((A,B)I,(C,(D,E)J)K)R;", parser=1)
        output_add_prop_ids(t)
        nodes = _by_name(t)
        # R's rightmost internal descendant is J (id=4) via K.
        assert nodes["R"].props["node_rgt"] == 4
        # K's rightmost internal descendant is J (id=4).
        assert nodes["K"].props["node_rgt"] == 4

    def test_unnamed_internal_nodes_still_get_props(self):
        # The function keys off is_leaf, not the node name, so unnamed
        # internal nodes still receive the id props.
        t = ete4.Tree("(C,(A,B));", parser=1)
        output_add_prop_ids(t)
        internals = [n for n in t.traverse("preorder") if not n.is_leaf]
        assert [n.props["id"] for n in internals] == [1, 2]
        # Root (id=1) spans all three leaves; its rightmost internal
        # descendant is the (A,B) subtree (id=2).
        assert internals[0].props["leaf_lft"] == 1
        assert internals[0].props["leaf_rgt"] == 3
        assert internals[0].props["node_rgt"] == 2
        # (A,B) (id=2) spans leaves 2..3; terminal, so node_rgt is itself.
        assert internals[1].props["leaf_lft"] == 2
        assert internals[1].props["leaf_rgt"] == 3
        assert internals[1].props["node_rgt"] == 2

    def test_relies_on_ascending_ladderization(self):
        # node_rgt is computed by walking postorder and trusting that the
        # last-visited child sits at the right of its parent — which holds
        # only when the tree is ladderized ascending (small subtree first,
        # so the rightmost child carries the largest subtree). If a leaf
        # sits to the right of an internal sibling, the function wrongly
        # treats the parent as terminal. This test pins that assumption.
        t = ete4.Tree("((A,B)I,C)R;", parser=1)  # descending: leaf C on the right
        output_add_prop_ids(t)
        nodes = _by_name(t)
        # R's true rightmost-internal descendant is I (id=2), but because
        # C is the rightmost child the function records R as terminal.
        assert nodes["R"].props["id"] == 1
        assert nodes["R"].props["node_rgt"] == 1

    def test_deeply_nested_ladder(self):
        # A right-leaning ladder: each level's rightmost child is the
        # bigger subtree, so node_rgt should chain down to the deepest
        # internal node.
        t = ete4.Tree("(A,(B,(C,(D,E)J)K)L)R;", parser=1)
        output_add_prop_ids(t)
        nodes = _by_name(t)
        # Preorder of internals: R, L, K, J → ids 1, 2, 3, 4.
        assert nodes["R"].props["id"] == 1
        assert nodes["L"].props["id"] == 2
        assert nodes["K"].props["id"] == 3
        assert nodes["J"].props["id"] == 4
        # Every ancestor's rightmost internal descendant is J.
        assert nodes["R"].props["node_rgt"] == 4
        assert nodes["L"].props["node_rgt"] == 4
        assert nodes["K"].props["node_rgt"] == 4
        assert nodes["J"].props["node_rgt"] == 4  # terminal → self
        # leaf_lft / leaf_rgt span the leaves below each node.
        assert nodes["R"].props["leaf_lft"] == 1
        assert nodes["R"].props["leaf_rgt"] == 5
        assert nodes["L"].props["leaf_lft"] == 2
        assert nodes["L"].props["leaf_rgt"] == 5
        assert nodes["K"].props["leaf_lft"] == 3
        assert nodes["K"].props["leaf_rgt"] == 5
        assert nodes["J"].props["leaf_lft"] == 4
        assert nodes["J"].props["leaf_rgt"] == 5

    def test_leaf_lft_leq_leaf_rgt_for_every_internal(self):
        # Sanity invariant — leftmost-leaf position never exceeds the
        # rightmost-leaf position within the same subtree.
        t = ete4.Tree("((A,B)I,(C,(D,E)J)K)R;", parser=1)
        output_add_prop_ids(t)
        for n in t.traverse():
            if n.is_leaf:
                continue
            assert n.props["leaf_lft"] <= n.props["leaf_rgt"]

    def test_node_rgt_never_exceeds_max_internal_id(self):
        # node_rgt always points at an existing internal node id, so it
        # cannot exceed the count of internal nodes.
        t = ete4.Tree("((A,B)I,(C,(D,E)J)K)R;", parser=1)
        output_add_prop_ids(t)
        internals = [n for n in t.traverse() if not n.is_leaf]
        max_id = max(n.props["id"] for n in internals)
        for n in internals:
            assert 1 <= n.props["node_rgt"] <= max_id


# Header columns in the order written by output_mysqlexport.
LEAF_HEADER = [
    "parent",
    "real_parent",
    "name",
    "extinction_date",
    "ott",
    "wikidata",
    "wikipedia_lang_flag",
    "iucn",
    "eol",
    "raw_popularity",
    "popularity",
    "popularity_rank",
    "price",
    "ncbi",
    "ifung",
    "worms",
    "irmng",
    "gbif",
    "ipni",
]

NODE_HEADER = (
    [
        "parent",
        "real_parent",
        "node_rgt",
        "leaf_lft",
        "leaf_rgt",
        "name",
        "age",
        "ott",
        "wikidata",
        "wikipedia_lang_flag",
        "eol",
        "rnk",
        "raw_popularity",
        "popularity",
        "ncbi",
        "ifung",
        "worms",
        "irmng",
        "gbif",
        "ipni",
        "vern_synth",
    ]
    + [rit + str(i + 1) for rit in ("rep", "rtr", "rpd") for i in range(8)]
    + ["iucn" + t for t in ("NE", "DD", "LC", "NT", "VU", "EN", "CR", "EW", "EX")]
)


class TestOutputMysqlExport:
    def test_creates_three_output_files(self, tmp_path):
        t = ete4.Tree("(A,B)R;", parser=1)
        _prep(t)
        output_mysqlexport(t, str(tmp_path))
        assert (tmp_path / "ordered_leaves.csv").exists()
        assert (tmp_path / "ordered_nodes.csv").exists()
        assert (tmp_path / "import.sql").exists()

    def test_leaf_header_matches_expected_columns(self, tmp_path):
        t = ete4.Tree("(A,B)R;", parser=1)
        _prep(t)
        output_mysqlexport(t, str(tmp_path))
        rows = _read_csv(tmp_path, "ordered_leaves.csv")
        assert rows[0] == LEAF_HEADER

    def test_node_header_matches_expected_columns(self, tmp_path):
        t = ete4.Tree("(A,B)R;", parser=1)
        _prep(t)
        output_mysqlexport(t, str(tmp_path))
        rows = _read_csv(tmp_path, "ordered_nodes.csv")
        assert rows[0] == NODE_HEADER

    def test_leaf_and_node_row_widths_match_their_headers(self, tmp_path):
        # Each emitted row must have exactly as many fields as its header,
        # otherwise MySQL's LOAD DATA INFILE will reject it.
        t = ete4.Tree("((A,B)I,(C,(D,E)J)K)R;", parser=1)
        _prep(t)
        output_mysqlexport(t, str(tmp_path))
        leaves = _read_csv(tmp_path, "ordered_leaves.csv")
        nodes = _read_csv(tmp_path, "ordered_nodes.csv")
        for row in leaves[1:]:
            assert len(row) == len(LEAF_HEADER)
        for row in nodes[1:]:
            assert len(row) == len(NODE_HEADER)

    def test_leaves_go_to_leaf_csv_internals_to_node_csv(self, tmp_path):
        # Five leaves under four internal nodes → 5 data rows in leaves,
        # 4 data rows in nodes.
        t = ete4.Tree("((A,B)I,(C,(D,E)J)K)R;", parser=1)
        _prep(t)
        output_mysqlexport(t, str(tmp_path))
        leaves = _read_csv(tmp_path, "ordered_leaves.csv")
        nodes = _read_csv(tmp_path, "ordered_nodes.csv")
        leaf_names = [r[LEAF_HEADER.index("name")] for r in leaves[1:]]
        node_names = [r[NODE_HEADER.index("name")] for r in nodes[1:]]
        assert sorted(leaf_names) == ["A", "B", "C", "D", "E"]
        assert sorted(node_names) == ["I", "J", "K", "R"]

    def test_leaf_rows_are_in_preorder(self, tmp_path):
        # The function traverses preorder; leaf rows should reflect that.
        t = ete4.Tree("((A,B)I,(C,(D,E)J)K)R;", parser=1)
        _prep(t)
        output_mysqlexport(t, str(tmp_path))
        leaves = _read_csv(tmp_path, "ordered_leaves.csv")
        leaf_names = [r[LEAF_HEADER.index("name")] for r in leaves[1:]]
        assert leaf_names == ["A", "B", "C", "D", "E"]

    def test_leaf_name_strips_ott_suffix(self, tmp_path):
        # The "_ottNNN" suffix carries the OTT id and is removed from the
        # name written to the CSV.
        t = ete4.Tree("(A_ott1234,B_ott5678)R;", parser=1)
        _prep(t)
        output_mysqlexport(t, str(tmp_path))
        leaves = _read_csv(tmp_path, "ordered_leaves.csv")
        names = [r[LEAF_HEADER.index("name")] for r in leaves[1:]]
        assert names == ["A", "B"]

    def test_root_parent_field_is_backslash_N(self, tmp_path):
        # Root has no parent → "parent" column is \N (MySQL NULL marker).
        t = ete4.Tree("(A,B)R;", parser=1)
        _prep(t)
        output_mysqlexport(t, str(tmp_path))
        nodes = _read_csv(tmp_path, "ordered_nodes.csv")
        root_row = next(r for r in nodes[1:] if r[NODE_HEADER.index("name")] == "R")
        assert root_row[NODE_HEADER.index("parent")] == "\\N"

    def test_root_real_parent_is_zero(self, tmp_path):
        # Root has no parent, so real_parent is the sentinel 0.
        t = ete4.Tree("(A,B)R;", parser=1)
        _prep(t)
        output_mysqlexport(t, str(tmp_path))
        nodes = _read_csv(tmp_path, "ordered_nodes.csv")
        root_row = next(r for r in nodes[1:] if r[NODE_HEADER.index("name")] == "R")
        assert root_row[NODE_HEADER.index("real_parent")] == "0"

    def test_non_root_parent_is_parent_id(self, tmp_path):
        # A leaf's "parent" field is the id of its (internal) parent.
        t = ete4.Tree("((A,B)I,(C,D)J)R;", parser=1)
        _prep(t)
        output_mysqlexport(t, str(tmp_path))
        nodes = _by_name(t)
        leaves = _read_csv(tmp_path, "ordered_leaves.csv")
        i_id = str(nodes["I"].props["id"])
        j_id = str(nodes["J"].props["id"])
        rows = {r[LEAF_HEADER.index("name")]: r for r in leaves[1:]}
        assert rows["A"][LEAF_HEADER.index("parent")] == i_id
        assert rows["B"][LEAF_HEADER.index("parent")] == i_id
        assert rows["C"][LEAF_HEADER.index("parent")] == j_id
        assert rows["D"][LEAF_HEADER.index("parent")] == j_id

    def test_node_row_writes_id_range_columns(self, tmp_path):
        # Internal nodes carry node_rgt / leaf_lft / leaf_rgt across to
        # their CSV row.
        t = ete4.Tree("((A,B)I,(C,(D,E)J)K)R;", parser=1)
        _prep(t)
        output_mysqlexport(t, str(tmp_path))
        nodes_by_name = _by_name(t)
        rows = _read_csv(tmp_path, "ordered_nodes.csv")
        by_name = {r[NODE_HEADER.index("name")]: r for r in rows[1:]}
        for nm in ("R", "I", "K", "J"):
            row = by_name[nm]
            n = nodes_by_name[nm]
            assert row[NODE_HEADER.index("node_rgt")] == str(n.props["node_rgt"])
            assert row[NODE_HEADER.index("leaf_lft")] == str(n.props["leaf_lft"])
            assert row[NODE_HEADER.index("leaf_rgt")] == str(n.props["leaf_rgt"])

    def test_taxon_props_are_written_to_leaf_row(self, tmp_path):
        # Values supplied via node.props["taxon"] are projected onto the
        # matching CSV columns; absent keys become \N.
        t = ete4.Tree("(A,B)R;", parser=1)
        _prep(
            t,
            taxon_overrides={
                "A": {
                    "ott": "111",
                    "wikidata": "Q1",
                    "iucn": "LC",
                    "eol": "42",
                    "ncbi": "999",
                },
            },
        )
        output_mysqlexport(t, str(tmp_path))
        leaves = _read_csv(tmp_path, "ordered_leaves.csv")
        rows = {r[LEAF_HEADER.index("name")]: r for r in leaves[1:]}
        a = rows["A"]
        assert a[LEAF_HEADER.index("ott")] == "111"
        assert a[LEAF_HEADER.index("wikidata")] == "Q1"
        assert a[LEAF_HEADER.index("iucn")] == "LC"
        assert a[LEAF_HEADER.index("eol")] == "42"
        assert a[LEAF_HEADER.index("ncbi")] == "999"
        # B had no overrides → \N everywhere taxon-derived.
        b = rows["B"]
        assert b[LEAF_HEADER.index("ott")] == "\\N"
        assert b[LEAF_HEADER.index("ncbi")] == "\\N"

    def test_taxon_props_are_written_to_node_row(self, tmp_path):
        # Internal nodes get the same taxon projection — but with `rnk`
        # in place of the leaf-only `iucn`/`extinction_date` columns.
        t = ete4.Tree("(A,B)R;", parser=1)
        _prep(t, taxon_overrides={"R": {"ott": "777", "rnk": "family"}})
        output_mysqlexport(t, str(tmp_path))
        nodes = _read_csv(tmp_path, "ordered_nodes.csv")
        root = next(r for r in nodes[1:] if r[NODE_HEADER.index("name")] == "R")
        assert root[NODE_HEADER.index("ott")] == "777"
        assert root[NODE_HEADER.index("rnk")] == "family"

    def test_missing_extinction_date_and_popularity_are_backslash_N(self, tmp_path):
        # Leaf-only props (extinction_date, popularity, popularity_rank)
        # default to \N when not set.
        t = ete4.Tree("(A,B)R;", parser=1)
        _prep(t)
        output_mysqlexport(t, str(tmp_path))
        leaves = _read_csv(tmp_path, "ordered_leaves.csv")
        for row in leaves[1:]:
            assert row[LEAF_HEADER.index("extinction_date")] == "\\N"
            assert row[LEAF_HEADER.index("popularity")] == "\\N"
            assert row[LEAF_HEADER.index("popularity_rank")] == "\\N"

    def test_leaf_extinction_date_and_popularity_are_emitted(self, tmp_path):
        # Values on the leaf itself flow through unchanged.
        t = ete4.Tree("(A,B)R;", parser=1)
        _prep(t)
        nodes = _by_name(t)
        nodes["A"].props["extinction_date"] = "2020"
        nodes["A"].props["popularity"] = 1.5
        nodes["A"].props["popularity_rank"] = 3
        output_mysqlexport(t, str(tmp_path))
        leaves = _read_csv(tmp_path, "ordered_leaves.csv")
        a = next(r for r in leaves[1:] if r[LEAF_HEADER.index("name")] == "A")
        assert a[LEAF_HEADER.index("extinction_date")] == "2020"
        assert a[LEAF_HEADER.index("popularity")] == "1.5"
        assert a[LEAF_HEADER.index("popularity_rank")] == "3"

    def test_internal_node_date_written_as_age(self, tmp_path):
        # An internal node's "date" property is exposed via the "age" column.
        t = ete4.Tree("(A,B)R;", parser=1)
        _prep(t)
        t.props["date"] = 12.5
        output_mysqlexport(t, str(tmp_path))
        nodes = _read_csv(tmp_path, "ordered_nodes.csv")
        root = next(r for r in nodes[1:] if r[NODE_HEADER.index("name")] == "R")
        assert root[NODE_HEADER.index("age")] == "12.5"

    def test_polytomy_parent_is_skipped_for_real_parent(self, tmp_path):
        # A non-polytomy node whose immediate parent has dist==0 (a
        # randomly-resolved polytomy node) should attribute its
        # real_parent to the next ancestor with dist!=0.
        # Tree shape: G -> P (dist=0 polytomy) -> X (dist=1 leaf).
        # X's real_parent must be G, not P.
        t = ete4.Tree("((X:1,Y:1)P:0,Z:1)G:1;", parser=1)
        nodes = _by_name(t)
        _prep(t)
        output_mysqlexport(t, str(tmp_path))
        leaves = _read_csv(tmp_path, "ordered_leaves.csv")
        x = next(r for r in leaves[1:] if r[LEAF_HEADER.index("name")] == "X")
        # parent (raw) is still P; real_parent skips it up to G.
        assert x[LEAF_HEADER.index("parent")] == str(nodes["P"].props["id"])
        assert x[LEAF_HEADER.index("real_parent")] == str(nodes["G"].props["id"])

    def test_polytomy_self_emits_negative_real_parent(self, tmp_path):
        # A node that is itself a polytomy resolution (dist=0) writes a
        # negative real_parent_id, flagging the relationship as artificial.
        t = ete4.Tree("((X:1,Y:1)P:0,Z:1)G:1;", parser=1)
        nodes = _by_name(t)
        _prep(t)
        output_mysqlexport(t, str(tmp_path))
        node_rows = _read_csv(tmp_path, "ordered_nodes.csv")
        p = next(r for r in node_rows[1:] if r[NODE_HEADER.index("name")] == "P")
        # P's dist is 0; G is its (non-polytomy) parent.
        assert p[NODE_HEADER.index("real_parent")] == str(-nodes["G"].props["id"])

    def test_import_sql_contains_load_data_for_both_tables(self, tmp_path):
        # The SQL script should truncate-and-load both CSV files. The
        # column list inside `LOAD DATA INFILE` is read from the first
        # line of the CSV, so it must match the CSV header exactly.
        t = ete4.Tree("(A,B)R;", parser=1)
        _prep(t)
        output_mysqlexport(t, str(tmp_path))
        sql = (tmp_path / "import.sql").read_text(encoding="utf-8")
        assert "TRUNCATE TABLE ordered_leaves;" in sql
        assert "TRUNCATE TABLE ordered_nodes;" in sql
        assert "LOAD DATA LOCAL INFILE 'ordered_leaves.csv'" in sql
        assert "LOAD DATA LOCAL INFILE 'ordered_nodes.csv'" in sql
        # Header echoed inside the LOAD DATA column list.
        assert "(" + ",".join(LEAF_HEADER) + ")" in sql
        assert "(" + ",".join(NODE_HEADER) + ")" in sql
        # `id` is auto-assigned by MySQL, not loaded from CSV.
        assert "SET id = NULL;" in sql


######


def build_tree(nwk, prop_name, prop_values, prop_format="u8"):
    """Parse (nwk), assigning node.props[prop_name] = prop_values[node.name] where set."""
    t = ete4.Tree(nwk, parser=1)
    for node in t.traverse("preorder"):
        if node.name in prop_values:
            node.props[prop_name] = prop_values[node.name]

    t.root.props.setdefault("prop_format", {})[prop_name] = prop_format

    return t


def read_packed(path, pack_format):
    sz = struct.calcsize("<" + pack_format)
    with open(path, "rb") as f:
        data = f.read()
    assert len(data) % sz == 0
    n = len(data) // sz
    return list(struct.unpack("<" + pack_format * n, data))


class TestOutputPropArray:
    def test_int_packing(self, tmp_path):
        """Integer properties pack as unsigned bytes; leaves and internals split into separate files in preorder."""
        t = build_tree(
            "((a,b)x,c)root;",
            "myprop",
            {"root": 5, "x": 12, "a": 1, "b": 2, "c": 3},
            prop_format="u8",
        )
        leaf_path, node_path = output_proparray(t, str(tmp_path), "myprop")

        assert leaf_path == str(tmp_path / "myprop_leaves_u8.dat")
        assert node_path == str(tmp_path / "myprop_nodes_u8.dat")

        # Preorder: root, x, a, b, c -> leaves [a, b, c], internals [root, x]
        assert read_packed(leaf_path, "B") == [1, 2, 3]
        assert read_packed(node_path, "B") == [5, 12]

    def test_float_packing(self, tmp_path):
        """Float properties pack as 2-byte half-floats."""
        t = build_tree(
            "((a,b)x,c)root;",
            "myprop",
            {"root": 5.0, "x": 12.0, "a": 1.0, "b": 2.0, "c": 3.0},
            prop_format="f32",
        )
        leaf_path, node_path = output_proparray(t, str(tmp_path), "myprop")

        assert leaf_path == str(tmp_path / "myprop_leaves_f32.dat")
        assert node_path == str(tmp_path / "myprop_nodes_f32.dat")

        assert struct.calcsize("<f") == 4
        assert read_packed(leaf_path, "f") == [1.0, 2.0, 3.0]
        assert read_packed(node_path, "f") == [5.0, 12.0]

    def test_preorder_matches_traversal(self, tmp_path):
        """Order of packed values follows preorder traversal of leaves / internals."""
        # Asymmetric tree to make ordering unambiguous
        t = build_tree(
            "(((a,b)x,c)y,(d,e)z)root;",
            "p",
            {"root": 100, "y": 50, "x": 25, "a": 1, "b": 2, "c": 3, "z": 75, "d": 4, "e": 5},
            prop_format="u8",
        )
        leaf_path, node_path = output_proparray(t, str(tmp_path), "p")

        # Preorder visits: root, y, x, a, b, c, z, d, e
        assert read_packed(leaf_path, "B") == [1, 2, 3, 4, 5]
        assert read_packed(node_path, "B") == [100, 50, 25, 75]

    def test_unsupported_type_raises(self, tmp_path):
        """Non-numeric property type raises ValueError."""
        t = build_tree(
            "(a,b)root;",
            "myprop",
            {"root": "hello", "a": "x", "b": "y"},
            prop_format="z99",
        )
        with pytest.raises(ValueError, match="z99"):
            output_proparray(t, str(tmp_path), "myprop")
