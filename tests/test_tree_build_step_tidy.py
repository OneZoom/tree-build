import ete4

from oz_tree_build.tree_build.step_tidy import (
    tidy_clear_conflicting_dates_topdown,
    tidy_infill_dates_bottomup,
)


def _by_name(tree):
    return {n.name: n for n in tree.traverse()}


class TestTidyInfillDatesBottomup:
    def test_single_leaf_gets_date_zero(self):
        t = ete4.Tree("A;", parser=1)
        tidy_infill_dates_bottomup(t)
        assert t.props["date"] == 0

    def test_all_leaves_get_date_zero(self):
        # Every leaf is reset to 0 regardless of any earlier value.
        t = ete4.Tree("(A:1,B:2)Root;", parser=1)
        nodes = _by_name(t)
        nodes["A"].props["date"] = 99  # will be overwritten
        tidy_infill_dates_bottomup(t)
        assert nodes["A"].props["date"] == 0
        assert nodes["B"].props["date"] == 0

    def test_parent_date_is_max_child_branch_length(self):
        # Root date = max(child.date + child.dist) over leaves at date 0.
        t = ete4.Tree("(A:1,B:2)Root;", parser=1)
        tidy_infill_dates_bottomup(t)
        assert t.props["date"] == 2

    def test_multilevel_tree_accumulates_branch_lengths(self):
        t = ete4.Tree("((A:1,B:2):3,C:4)Root;", parser=1)
        tidy_infill_dates_bottomup(t)
        # Internal (parent of A,B) = max(0+1, 0+2) = 2
        # Root = max(2+3, 0+4) = 5
        internal = next(c for c in t.children if not c.is_leaf)
        assert internal.props["date"] == 2
        assert t.props["date"] == 5

    def test_existing_internal_date_preserved_when_larger(self):
        # Pre-existing date on an internal node is kept if no child's
        # accumulated date exceeds it.
        t = ete4.Tree("((A:1,B:2):3,C:4)Root;", parser=1)
        internal = next(c for c in t.children if not c.is_leaf)
        internal.props["date"] = 100
        tidy_infill_dates_bottomup(t)
        assert internal.props["date"] == 100
        # Root sees the preserved internal date: max(100+3, 0+4) = 103
        assert t.props["date"] == 103

    def test_existing_internal_date_overwritten_when_smaller(self):
        # A child-derived date larger than the pre-existing one wins.
        t = ete4.Tree("((A:1,B:2):3,C:4)Root;", parser=1)
        internal = next(c for c in t.children if not c.is_leaf)
        internal.props["date"] = 0.5
        tidy_infill_dates_bottomup(t)
        assert internal.props["date"] == 2
        assert t.props["date"] == 5

    def test_child_without_dist_does_not_contribute(self):
        # A child whose dist is None must not bump its parent's date.
        t = ete4.Tree("(A,B:5)Root;", parser=1)
        tidy_infill_dates_bottomup(t)
        # Only B contributes: Root = 0 + 5 = 5
        assert t.props["date"] == 5

    def test_internal_without_datable_descendants_has_no_date(self):
        # If every child of an internal lacks dist, the internal stays
        # without a date and cannot in turn propagate upward.
        t = ete4.Tree("((A,B):4,C:1)Root;", parser=1)
        tidy_infill_dates_bottomup(t)
        internal = next(c for c in t.children if not c.is_leaf)
        # Internal has no datable children (A and B both lack dist).
        assert internal.props.get("date") is None
        # Root sees only C contributing (internal has no date).
        assert t.props["date"] == 1

    def test_picks_oldest_subtree_when_branches_differ(self):
        # Two subtrees with different total ages — root takes the older.
        t = ete4.Tree("((A:1,B:1):10,(C:1,D:1):2)Root;", parser=1)
        tidy_infill_dates_bottomup(t)
        # left subtree internal = 1, +10 = 11; right subtree internal = 1, +2 = 3
        assert t.props["date"] == 11


class TestTidyClearConflictingDatesTopdown:
    def test_consistent_dates_are_all_kept(self):
        # Descending dates: root oldest, leaves youngest. Nothing removed.
        t = ete4.Tree("((A,B)I,C)Root;", parser=1)
        nodes = _by_name(t)
        nodes["Root"].props["date"] = 10
        nodes["I"].props["date"] = 5
        nodes["A"].props["date"] = 0
        nodes["B"].props["date"] = 2
        nodes["C"].props["date"] = 3
        tidy_clear_conflicting_dates_topdown(t)
        assert nodes["Root"].props["date"] == 10
        assert nodes["I"].props["date"] == 5
        assert nodes["A"].props["date"] == 0
        assert nodes["B"].props["date"] == 2
        assert nodes["C"].props["date"] == 3

    def test_child_older_than_parent_is_cleared(self):
        # A child date that is older than its ancestor is a conflict
        # and must be removed.
        t = ete4.Tree("(A,B)Root;", parser=1)
        nodes = _by_name(t)
        nodes["Root"].props["date"] = 10
        nodes["A"].props["date"] = 20  # older than Root — conflict
        nodes["B"].props["date"] = 3
        tidy_clear_conflicting_dates_topdown(t)
        assert "date" not in nodes["A"].props
        assert nodes["B"].props["date"] == 3
        assert nodes["Root"].props["date"] == 10

    def test_conflict_clears_only_that_node(self):
        # Removing an intermediate conflicting date should not stop the
        # descent — its descendants are still compared against the
        # original ancestor's date.
        t = ete4.Tree("((A,B)I,C)Root;", parser=1)
        nodes = _by_name(t)
        nodes["Root"].props["date"] = 10
        nodes["I"].props["date"] = 20  # conflict — older than Root
        nodes["A"].props["date"] = 5  # consistent with Root (10)
        nodes["B"].props["date"] = 50  # conflict — older than Root
        tidy_clear_conflicting_dates_topdown(t)
        assert nodes["Root"].props["date"] == 10
        assert "date" not in nodes["I"].props
        assert nodes["A"].props["date"] == 5
        assert "date" not in nodes["B"].props

    def test_missing_ancestor_date_does_not_constrain_descendants(self):
        # With no ancestor date set, the first node we meet on each path
        # establishes the ceiling for everything below it.
        t = ete4.Tree("(A,(B,C)I)Root;", parser=1)
        nodes = _by_name(t)
        # Root has no date.
        nodes["A"].props["date"] = 100  # nothing above — kept
        nodes["I"].props["date"] = 50
        nodes["B"].props["date"] = 1
        nodes["C"].props["date"] = 200  # conflict — older than I (50)
        tidy_clear_conflicting_dates_topdown(t)
        assert nodes["A"].props["date"] == 100
        assert nodes["I"].props["date"] == 50
        assert nodes["B"].props["date"] == 1
        assert "date" not in nodes["C"].props

    def test_nodes_without_date_are_skipped_and_pass_mrad_through(self):
        # An intermediate node without a date must not reset the ceiling;
        # its descendants are still compared against the nearest ancestor
        # that does have a date.
        t = ete4.Tree("((A)I)Root;", parser=1)
        nodes = _by_name(t)
        nodes["Root"].props["date"] = 10
        # I has no date.
        nodes["A"].props["date"] = 50  # still in conflict with Root via I
        tidy_clear_conflicting_dates_topdown(t)
        assert nodes["Root"].props["date"] == 10
        assert "date" not in nodes["I"].props
        assert "date" not in nodes["A"].props

    def test_small_overshoot_within_tolerance_is_kept(self):
        # The function tolerates floating-point noise up to 1e-5.
        t = ete4.Tree("(A)Root;", parser=1)
        nodes = _by_name(t)
        nodes["Root"].props["date"] = 10
        nodes["A"].props["date"] = 10 + 1e-6  # just within tolerance
        tidy_clear_conflicting_dates_topdown(t)
        assert nodes["A"].props["date"] == 10 + 1e-6

    def test_overshoot_beyond_tolerance_is_cleared(self):
        t = ete4.Tree("(A)Root;", parser=1)
        nodes = _by_name(t)
        nodes["Root"].props["date"] = 10
        nodes["A"].props["date"] = 10 + 1e-3  # outside tolerance
        tidy_clear_conflicting_dates_topdown(t)
        assert "date" not in nodes["A"].props

    def test_equal_dates_are_kept(self):
        # parent.date == ancestor.date is not a conflict.
        t = ete4.Tree("(A)Root;", parser=1)
        nodes = _by_name(t)
        nodes["Root"].props["date"] = 10
        nodes["A"].props["date"] = 10
        tidy_clear_conflicting_dates_topdown(t)
        assert nodes["A"].props["date"] == 10

    def test_mrad_tightens_as_we_descend(self):
        # After we descend past a node with a smaller date, that smaller
        # date becomes the new ceiling for everything below.
        t = ete4.Tree("((A,B)I)Root;", parser=1)
        nodes = _by_name(t)
        nodes["Root"].props["date"] = 100
        nodes["I"].props["date"] = 5  # tighter than Root
        nodes["A"].props["date"] = 3  # below I — fine
        nodes["B"].props["date"] = 50  # would be fine vs Root but conflicts with I
        tidy_clear_conflicting_dates_topdown(t)
        assert nodes["A"].props["date"] == 3
        assert "date" not in nodes["B"].props

    def test_runs_on_tree_with_no_dates_at_all(self):
        # Nothing to do; should not raise.
        t = ete4.Tree("((A,B),C)Root;", parser=1)
        tidy_clear_conflicting_dates_topdown(t)
        for n in t.traverse():
            assert n.props.get("date") is None


class TestTidyPipeline:
    def test_bottomup_then_topdown_on_clean_tree_is_stable(self):
        # End-to-end: branch-length-derived dates should already be
        # self-consistent, so the topdown pass changes nothing.
        t = ete4.Tree("((A:1,B:2):3,C:4)Root;", parser=1)
        tidy_infill_dates_bottomup(t)
        before = {id(n): n.props.get("date") for n in t.traverse()}
        tidy_clear_conflicting_dates_topdown(t)
        after = {id(n): n.props.get("date") for n in t.traverse()}
        assert before == after

    def test_bottomup_then_topdown_clears_oversized_pin(self):
        # If a pre-pinned internal date is older than the root's
        # inferred date, the topdown pass should strip it.
        t = ete4.Tree("((A:1,B:2):3,C:4)Root;", parser=1)
        internal = next(c for c in t.children if not c.is_leaf)
        internal.props["date"] = 100  # pin older than root could ever be
        tidy_infill_dates_bottomup(t)
        # Root is forced up to 103 by the pin; that's fine.
        # Now imagine an externally fixed Root date that's smaller:
        t.props["date"] = 50
        tidy_clear_conflicting_dates_topdown(t)
        assert t.props["date"] == 50
        assert "date" not in internal.props
