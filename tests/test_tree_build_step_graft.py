import ete4

from oz_tree_build.tree_build.step_graft import graft_extract_ot_subtrees, graft_tree, present_in_tree


class TestGraftTree:
    def test_no_inclusions_is_noop(self):
        t = ete4.Tree("(A_ott1,B_ott2)Root_ott3;", parser=1)
        missing = graft_tree(t, {})
        assert missing == []
        assert t.write() == "(A_ott1,B_ott2);"

    def test_simple_graft(self):
        # The grafted node inherits the subtree's children and its dist.
        t = ete4.Tree("(A_ott99,Sub_ott1@)Root;", parser=1)
        sub = ete4.Tree("(X_ott11,Y_ott12)SubRoot_ott1;", parser=1)
        sub.root.dist = 3.5

        missing = graft_tree(t, {"Sub_ott1@": sub})

        assert missing == []
        assert t.write() == "(A_ott99,(X_ott11,Y_ott12):3.5);"

    def test_missing_inclusion_reported(self):
        t = ete4.Tree("(A_ott99,Sub_ott1@)Root;", parser=1)
        missing = graft_tree(t, {})
        assert missing == ["Sub_ott1@"]
        # Original tree untouched at the inclusion point.
        assert t.write() == "(A_ott99,Sub_ott1@);"

    def test_multiple_missing_inclusions(self):
        t = ete4.Tree("(A_ott1@,(B_ott2@,C_ott3@)Sub)Root;", parser=1)
        missing = graft_tree(t, {})
        assert sorted(missing) == ["A_ott1@", "B_ott2@", "C_ott3@"]

    def test_prefer_subtree_name_uses_subroot_name(self):
        # With prefer_subtree_name=True, the subtree's root name wins.
        t = ete4.Tree("(A_ott99,Sub_ott1@)Root;", parser=1)
        sub = ete4.Tree("(X_ott11,Y_ott12)SubRoot_ott1;", parser=1)

        graft_tree(t, {"Sub_ott1@": sub}, prefer_subtree_name=True)

        grafted_names = [n.name for n in t.traverse() if not n.is_leaf and n.name]
        assert "SubRoot_ott1" in grafted_names

    def test_prefer_subtree_name_falls_back_when_subroot_unnamed(self):
        # If the subtree's root is unnamed, fall back to the inclusion's
        # derived node_name ("Sub ott1").
        t = ete4.Tree("(A_ott99,Sub_ott1@)Root;", parser=1)
        sub = ete4.Tree("(X_ott11,Y_ott12);", parser=1)

        graft_tree(t, {"Sub_ott1@": sub}, prefer_subtree_name=True)

        grafted_names = [n.name for n in t.traverse() if not n.is_leaf and n.name]
        assert "Sub ott1" in grafted_names

    def test_recursion_resolves_nested_inclusions(self):
        t = ete4.Tree("(A_ott99,Sub_ott1@)Root;", parser=1)
        sub = ete4.Tree("(X_ott11,Inner_ott2@)SubRoot;", parser=1)
        inner = ete4.Tree("(I1_ott21,I2_ott22)InnerRoot;", parser=1)

        missing = graft_tree(t, {"Sub_ott1@": sub, "Inner_ott2@": inner})

        assert missing == []
        assert t.write() == "(A_ott99,(X_ott11,(I1_ott21,I2_ott22)));"

    def test_disable_recursion_leaves_nested_inclusions(self):
        # disable_recursion=True skips the inner graft_tree call, so the
        # nested inclusion token is left in place and not reported missing
        # (since the traversal treats the grafted node as a leaf).
        t = ete4.Tree("(A_ott99,Sub_ott1@)Root;", parser=1)
        sub = ete4.Tree("(X_ott11,Inner_ott2@)SubRoot;", parser=1)
        inner = ete4.Tree("(I1_ott21,I2_ott22)InnerRoot;", parser=1)

        missing = graft_tree(
            t,
            {"Sub_ott1@": sub, "Inner_ott2@": inner},
            disable_recursion=True,
        )

        assert missing == []
        assert t.write() == "(A_ott99,(X_ott11,Inner_ott2@));"

    def test_recursion_reports_missing_from_nested(self):
        # A nested inclusion that has no provided subtree is reported.
        t = ete4.Tree("(A_ott99,Sub_ott1@)Root;", parser=1)
        sub = ete4.Tree("(X_ott11,Missing_ott2@)SubRoot;", parser=1)

        missing = graft_tree(t, {"Sub_ott1@": sub})

        assert missing == ["Missing_ott2@"]

    def test_subtree_props_copied(self):
        # Non-None props from the subtree root are copied onto the grafted node.
        t = ete4.Tree("(A_ott99,Sub_ott1@)Root;", parser=1)
        sub = ete4.Tree("(X_ott11,Y_ott12)SubRoot_ott1;", parser=1)
        sub.root.props["custom_prop"] = "hello"

        graft_tree(t, {"Sub_ott1@": sub})

        grafted = next(n for n in t.traverse() if n.props.get("custom_prop") == "hello")
        assert grafted is not None


class TestGraftExtractOtSubtrees:
    def test_extracts_subtrees_by_base_ott(self, tmp_path):
        ot_file = tmp_path / "ot.nwk"
        ot_file.write_text("(((X1_ott11,X2_ott12)Sub1_ott1,(Y1_ott21,Y2_ott22)Sub2_ott2)Inner_ott3,Z_ott4)Root_ott99;")
        result = graft_extract_ot_subtrees(ete4.Tree(str(ot_file), parser=1), ["Sub1_ott1@", "Sub2_ott2@"])
        assert set(result.keys()) == {"Sub1_ott1@", "Sub2_ott2@"}
        assert result["Sub1_ott1@"].write() == "(X1_ott11,X2_ott12);"
        assert result["Sub2_ott2@"].write() == "(Y1_ott21,Y2_ott22);"

    def test_missing_otts_not_in_result(self, tmp_path):
        ot_file = tmp_path / "ot.nwk"
        ot_file.write_text("((A_ott1,B_ott2)Sub_ott3)Root_ott4;")
        result = graft_extract_ot_subtrees(ete4.Tree(str(ot_file), parser=1), ["NotThere_ott99@"])
        assert result == {}

    def test_renaming_inclusion_uses_orig_name_as_key(self, tmp_path):
        # The key is the original inclusion string, including any rebase syntax.
        ot_file = tmp_path / "ot.nwk"
        ot_file.write_text("((A_ott1,B_ott2)Sub_ott5,C_ott3)Root_ott99;")
        result = graft_extract_ot_subtrees(ete4.Tree(str(ot_file), parser=1), ["Renamed_ott~5@"])
        assert list(result.keys()) == ["Renamed_ott~5@"]
        assert result["Renamed_ott~5@"].write() == "(A_ott1,B_ott2);"

    def test_recurses_into_extracted_subtrees(self, tmp_path):
        # If an extracted subtree itself contains another requested OTT, that
        # nested subtree is also extracted.
        ot_file = tmp_path / "ot.nwk"
        ot_file.write_text("(((((I1_ott11,I2_ott12)Inner_ott1)Filler_ott99)Sub_ott2)Outer_ott3)Root_ott99;")
        result = graft_extract_ot_subtrees(ete4.Tree(str(ot_file), parser=1), ["Outer_ott2@", "Nested_ott1@"])
        assert set(result.keys()) == {"Outer_ott2@", "Nested_ott1@"}
        assert result["Nested_ott1@"].write() == "(I1_ott11,I2_ott12);"
        # NB: Outer tree no longer contains inner tree
        assert result["Outer_ott2@"].write() == "(Filler_ott99);"


class TestPresentInTree:
    def test_finds_matching_node(self):
        t = ete4.Tree("(A_ott99,(Sub_ott1,C_ott4)B_ott7)Root_ott42;", parser=1)
        n = present_in_tree(t, "Anything_ott1@")
        assert n is not None
        assert n.name == "Sub_ott1"

    def test_matches_internal_node(self):
        t = ete4.Tree("(A_ott99,(Sub_ott1,C_ott4)B_ott7)Root_ott42;", parser=1)
        n = present_in_tree(t, "Anything_ott7@")
        assert n is not None
        assert n.name == "B_ott7"

    def test_returns_none_when_absent(self):
        t = ete4.Tree("(A_ott99,(Sub_ott1,C_ott4)B_ott7)Root_ott42;", parser=1)
        assert present_in_tree(t, "Anything_ott999@") is None

    def test_matches_root(self):
        t = ete4.Tree("(A_ott99,B_ott7)Root_ott42;", parser=1)
        n = present_in_tree(t, "Anything_ott42@")
        assert n is not None
        assert n.name == "Root_ott42"
