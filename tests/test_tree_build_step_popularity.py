import csv
from math import log

import ete4
import pytest

from oz_tree_build.taxon_mapping_and_popularity.taxon_map import read_taxon_map
from oz_tree_build.tree_build.step_popularity import (
    popularity_add_prop,
    popularity_add_rank,
    popularity_function,
    sum_popularity_over_tree,
)
from oz_tree_build.tree_build.step_taxon import taxon_add_prop

TAXON_CSV_FIELDS = [
    "ott",
    "wikidata",
    "wikipedia_lang_flag",
    "iucn",
    "eol",
    "rank",
    "raw_popularity",
    "ncbi",
    "if",
    "worms",
    "irmng",
    "gbif",
    "ipni",
]


def _attach_taxa(tmp_path, tree, rows):
    """Write ``rows`` to a CSV in the same shape as taxon_map.main produces,
    read it back with read_taxon_map, and attach to ``tree`` via taxon_add_prop.
    """
    path = tmp_path / "taxon.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, dialect="excel")
        w.writerow(TAXON_CSV_FIELDS)
        for row in rows:
            w.writerow([row.get(k, "") for k in TAXON_CSV_FIELDS])
    taxon_add_prop(tree, read_taxon_map(path))


class TestPopularityFunction:
    def test_returns_none_when_any_input_is_none(self):
        assert popularity_function(None, 1.0, 1, 1) is None
        assert popularity_function(1.0, None, 1, 1) is None
        assert popularity_function(1.0, 1.0, None, 1) is None
        assert popularity_function(1.0, 1.0, 1, None) is None

    def test_single_node_special_case_returns_sum(self):
        # n_ancestors + n_descendants == 1 dodges the log(1)=0 divide-by-zero
        # and just returns the sum of ancestor + descendant popsums.
        assert popularity_function(3.0, 7.0, 1, 0) == 10.0
        assert popularity_function(3.0, 7.0, 0, 1) == 10.0

    def test_general_case_divides_by_log_of_node_count(self):
        # (anc + desc) / log(n_anc + n_desc)
        assert popularity_function(10.0, 20.0, 1, 3) == pytest.approx(30.0 / log(4))


class TestSumPopularityOverTree:
    def test_pop_copied_from_taxon_raw_popularity(self, tmp_path):
        t = ete4.Tree("(A_ott1,B_ott2)Root_ott3;", parser=1)
        _attach_taxa(
            tmp_path,
            t,
            [
                {"ott": 1, "raw_popularity": 10.0},
                {"ott": 2, "raw_popularity": 20.0},
                {"ott": 3, "raw_popularity": 30.0},
            ],
        )

        sum_popularity_over_tree(t)

        by_name = {n.name: n for n in t.traverse()}
        assert by_name["A_ott1"].props["pop"] == 10.0
        assert by_name["A_ott1"].props["has_pop"] is True
        assert by_name["B_ott2"].props["pop"] == 20.0
        assert by_name["Root_ott3"].props["pop"] == 30.0

    def test_no_taxon_means_pop_zero(self, tmp_path):
        # A node with no matching taxon entry gets pop=0, has_pop=False.
        t = ete4.Tree("(A_ott1,B_ott2)Root_ott3;", parser=1)
        _attach_taxa(
            tmp_path,
            t,
            [
                {"ott": 1, "raw_popularity": 10.0},
            ],
        )

        sum_popularity_over_tree(t)

        b = next(n for n in t.traverse() if n.name == "B_ott2")
        assert b.props["pop"] == 0
        assert b.props["has_pop"] is False

    def test_taxon_present_but_raw_popularity_missing(self, tmp_path):
        # A taxon row exists for the node but its raw_popularity field is empty,
        # so read_taxon_map gives raw_popularity=None. The node should still
        # be treated as un-populated (pop=0, has_pop=False) rather than
        # propagating None as a popularity value.
        t = ete4.Tree("(A_ott1,B_ott2)Root_ott3;", parser=1)
        _attach_taxa(
            tmp_path,
            t,
            [
                {"ott": 1, "raw_popularity": 10.0},
                {"ott": 2, "wikidata": 42},  # row present, raw_popularity empty
                {"ott": 3, "raw_popularity": 30.0},
            ],
        )

        sum_popularity_over_tree(t)

        b = next(n for n in t.traverse() if n.name == "B_ott2")
        # Taxon dict is populated (wikidata is set) but raw_popularity is None.
        assert b.props["taxon"].get("wikidata") == 42
        assert b.props["taxon"].get("raw_popularity") is None
        assert b.props["pop"] == 0
        assert b.props["has_pop"] is False

    def test_descendant_sums_aggregate_upwards(self, tmp_path):
        t = ete4.Tree("(A_ott1,B_ott2)Root_ott3;", parser=1)
        _attach_taxa(
            tmp_path,
            t,
            [
                {"ott": 1, "raw_popularity": 10.0},
                {"ott": 2, "raw_popularity": 20.0},
                {"ott": 3, "raw_popularity": 30.0},
            ],
        )

        sum_popularity_over_tree(t)
        by_name = {n.name: n for n in t.traverse()}

        # Leaves: nothing beneath them.
        assert by_name["A_ott1"].props["descendants_popsum"] == 0
        assert by_name["A_ott1"].props["n_descendants"] == 0
        # Root: own pop excluded from descendants_popsum.
        assert by_name["Root_ott3"].props["descendants_popsum"] == 30.0
        assert by_name["Root_ott3"].props["n_descendants"] == 2

    def test_ancestor_sums_accumulate_downwards(self, tmp_path):
        t = ete4.Tree("(A_ott1,B_ott2)Root_ott3;", parser=1)
        _attach_taxa(
            tmp_path,
            t,
            [
                {"ott": 1, "raw_popularity": 10.0},
                {"ott": 2, "raw_popularity": 20.0},
                {"ott": 3, "raw_popularity": 30.0},
            ],
        )

        sum_popularity_over_tree(t)
        by_name = {n.name: n for n in t.traverse()}

        assert by_name["Root_ott3"].props["n_ancestors"] == 0
        assert by_name["Root_ott3"].props["ancestors_popsum"] == 0.0
        # ancestors_popsum at a child = parent.ancestors_popsum + own pop.
        assert by_name["A_ott1"].props["n_ancestors"] == 1
        assert by_name["A_ott1"].props["ancestors_popsum"] == 10.0
        assert by_name["B_ott2"].props["ancestors_popsum"] == 20.0

    def test_n_pop_ancestors_only_counts_nodes_with_pop(self, tmp_path):
        # Root has popularity, intermediate node does not, leaf does.
        t = ete4.Tree("((A_ott1)Mid_ott2)Root_ott3;", parser=1)
        _attach_taxa(
            tmp_path,
            t,
            [
                {"ott": 1, "raw_popularity": 5.0},
                # ott 2 deliberately missing -> has_pop=False at Mid
                {"ott": 3, "raw_popularity": 7.0},
            ],
        )

        sum_popularity_over_tree(t)
        by_name = {n.name: n for n in t.traverse()}

        # Root counts as a "pop ancestor" only when its own has_pop counts up
        # via descendants — n_pop_ancestors counts populated nodes on the way down.
        assert by_name["Mid_ott2"].props["n_pop_ancestors"] == 0  # mid itself missing
        assert by_name["A_ott1"].props["n_pop_ancestors"] == 1  # only A itself

    def test_exclude_taxa_zeroes_pop_for_named_node(self, tmp_path):
        # Excluded node's own pop becomes 0 / has_pop=False, but descendants
        # still contribute to its descendants_popsum (used by children below).
        t = ete4.Tree("(A_ott1,B_ott2)Root_ott3;", parser=1)
        _attach_taxa(
            tmp_path,
            t,
            [
                {"ott": 1, "raw_popularity": 10.0},
                {"ott": 2, "raw_popularity": 20.0},
                {"ott": 3, "raw_popularity": 999.0},
            ],
        )

        sum_popularity_over_tree(t, exclude_taxa=["Root_ott3"])
        root = next(n for n in t.traverse() if n.name == "Root_ott3")

        assert root.props["pop"] == 0
        assert root.props["has_pop"] is False
        # Children's pop still aggregates upwards.
        assert root.props["descendants_popsum"] == 30.0


class TestPopularityAddProp:
    def test_popularity_set_on_every_node_and_rounded(self, tmp_path):
        t = ete4.Tree("(A_ott1,B_ott2)Root_ott3;", parser=1)
        _attach_taxa(
            tmp_path,
            t,
            [
                {"ott": 1, "raw_popularity": 10.0},
                {"ott": 2, "raw_popularity": 20.0},
                {"ott": 3, "raw_popularity": 30.0},
            ],
        )

        popularity_add_prop(t)

        by_name = {n.name: n for n in t.traverse()}
        # Leaves: n_anc + n_desc == 1 -> sum of ancestor + descendant popsums.
        # A: anc=10, desc=0 -> 10. B: anc=20, desc=0 -> 20.
        assert by_name["A_ott1"].props["popularity"] == 10.0
        assert by_name["B_ott2"].props["popularity"] == 20.0
        # Root: (0 + 30) / log(2) — rounded to 2 dp.
        assert by_name["Root_ott3"].props["popularity"] == round(30.0 / log(2), 2)

    def test_nodes_without_pop_get_zero_popularity(self, tmp_path):
        # All zeros in -> popularity is 0 (special case applies at leaves).
        t = ete4.Tree("(A_ott1,B_ott2)Root_ott3;", parser=1)
        _attach_taxa(tmp_path, t, [])

        popularity_add_prop(t)
        for n in t.traverse():
            assert n.props["popularity"] == 0

    def test_exclude_taxa_passes_through(self, tmp_path):
        # popularity_add_prop forwards exclude_taxa to sum_popularity_over_tree;
        # the excluded node's own pop is zeroed so its rendered popularity
        # reflects only descendants.
        t = ete4.Tree("(A_ott1,B_ott2)Root_ott3;", parser=1)
        _attach_taxa(
            tmp_path,
            t,
            [
                {"ott": 1, "raw_popularity": 10.0},
                {"ott": 2, "raw_popularity": 20.0},
                {"ott": 3, "raw_popularity": 999.0},
            ],
        )

        popularity_add_prop(t, exclude_taxa=["Root_ott3"])
        root = next(n for n in t.traverse() if n.name == "Root_ott3")
        # Root pop=0, descendants_popsum=30, n_desc=2 -> 30/log(2).
        assert root.props["popularity"] == round(30.0 / log(2), 2)


class TestPopularityAddRank:
    @staticmethod
    def _set_leaf_pops(tree, pops):
        # Manually attach popularity values to leaves (bypassing the full
        # pipeline). popularity_add_rank only reads node.props["popularity"].
        for n in tree.traverse():
            if n.is_leaf and n.name in pops:
                n.props["popularity"] = pops[n.name]

    def test_distinct_popularities_get_sequential_ranks(self):
        # Higher popularity -> lower (better) rank, starting at 1.
        t = ete4.Tree("(A,B,C)R;", parser=1)
        self._set_leaf_pops(t, {"A": 30, "B": 20, "C": 10})

        popularity_add_rank(t)

        by_name = {n.name: n for n in t.traverse()}
        assert by_name["A"].props["popularity_rank"] == 1
        assert by_name["B"].props["popularity_rank"] == 2
        assert by_name["C"].props["popularity_rank"] == 3

    def test_ties_use_standard_competition_ranking(self):
        # Two leaves tied at the top share rank 1; the next leaf gets
        # rank 3 (not 2). Same for ties further down.
        t = ete4.Tree("(A,B,C,D,E)R;", parser=1)
        self._set_leaf_pops(t, {"A": 10, "B": 10, "C": 5, "D": 3, "E": 3})

        popularity_add_rank(t)

        by_name = {n.name: n for n in t.traverse()}
        assert by_name["A"].props["popularity_rank"] == 1
        assert by_name["B"].props["popularity_rank"] == 1
        assert by_name["C"].props["popularity_rank"] == 3
        assert by_name["D"].props["popularity_rank"] == 4
        assert by_name["E"].props["popularity_rank"] == 4

    def test_all_leaves_tied_share_rank_one(self):
        t = ete4.Tree("(A,B,C)R;", parser=1)
        self._set_leaf_pops(t, {"A": 7, "B": 7, "C": 7})

        popularity_add_rank(t)

        for name in ("A", "B", "C"):
            leaf = next(n for n in t.traverse() if n.name == name)
            assert leaf.props["popularity_rank"] == 1

    def test_single_leaf_gets_rank_one(self):
        # The function ranks even the root if it is a leaf.
        t = ete4.Tree("A;", parser=1)
        t.props["popularity"] = 42
        popularity_add_rank(t)
        assert t.props["popularity_rank"] == 1

    def test_internal_nodes_do_not_get_a_rank(self):
        # Only leaves are ranked; the internal node's popularity, even
        # if set, is ignored both as a tie-breaker and as an output.
        t = ete4.Tree("((A,B)I,C)R;", parser=1)
        self._set_leaf_pops(t, {"A": 10, "B": 5, "C": 1})
        by_name = {n.name: n for n in t.traverse()}
        by_name["I"].props["popularity"] = 999  # should not affect anything
        by_name["R"].props["popularity"] = 999

        popularity_add_rank(t)

        # Leaves ranked normally.
        assert by_name["A"].props["popularity_rank"] == 1
        assert by_name["B"].props["popularity_rank"] == 2
        assert by_name["C"].props["popularity_rank"] == 3
        # Internal nodes untouched by ranking.
        assert "popularity_rank" not in by_name["I"].props
        assert "popularity_rank" not in by_name["R"].props

    def test_internal_node_without_popularity_does_not_trigger_skip(self):
        # The None-guard only inspects leaves. An internal node that
        # has no popularity prop must not cause the early return.
        t = ete4.Tree("((A,B)I,C)R;", parser=1)
        self._set_leaf_pops(t, {"A": 10, "B": 5, "C": 1})
        # I and R deliberately have no popularity prop set.

        popularity_add_rank(t)

        by_name = {n.name: n for n in t.traverse()}
        assert by_name["A"].props["popularity_rank"] == 1
        assert by_name["B"].props["popularity_rank"] == 2
        assert by_name["C"].props["popularity_rank"] == 3

    def test_rank_cumsum_with_mixed_group_sizes(self):
        # 1 leaf at top, 3 tied below, 1 at the bottom.
        # Expected ranks: top=1, tied group=2, bottom=5.
        t = ete4.Tree("(A,B,C,D,E)R;", parser=1)
        self._set_leaf_pops(t, {"A": 100, "B": 50, "C": 50, "D": 50, "E": 1})

        popularity_add_rank(t)

        by_name = {n.name: n for n in t.traverse()}
        assert by_name["A"].props["popularity_rank"] == 1
        assert by_name["B"].props["popularity_rank"] == 2
        assert by_name["C"].props["popularity_rank"] == 2
        assert by_name["D"].props["popularity_rank"] == 2
        assert by_name["E"].props["popularity_rank"] == 5
