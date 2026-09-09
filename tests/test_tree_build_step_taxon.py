import ete4

from oz_tree_build.tree_build.step_taxon import taxon_add_prop


class TestTaxonAddProp:
    def test_empty_taxon_map_assigns_empty_dict(self):
        # Every node — leaf, internal, root — gets {} when the map is empty.
        t = ete4.Tree("(A_ott1,B_ott2)Root_ott3;", parser=1)
        taxon_add_prop(t, {})
        for n in t.traverse():
            assert n.props["taxon"] == {}

    def test_leaf_match_assigns_taxon_entry(self):
        t = ete4.Tree("(A_ott1,B_ott2)Root_ott3;", parser=1)
        a_entry = {"ott": 1, "wikidata": 42, "raw_popularity": 1.5}
        taxon_add_prop(t, {1: a_entry})

        a = next(n for n in t.traverse() if n.name == "A_ott1")
        b = next(n for n in t.traverse() if n.name == "B_ott2")
        assert a.props["taxon"] == a_entry
        assert b.props["taxon"] == {}

    def test_internal_node_match_assigns_taxon_entry(self):
        # Internal nodes are also looked up via their ottN suffix.
        t = ete4.Tree("(A_ott1,B_ott2)Root_ott3;", parser=1)
        root_entry = {"ott": 3, "rank": "family"}
        taxon_add_prop(t, {3: root_entry})

        root = next(n for n in t.traverse() if n.name == "Root_ott3")
        assert root.props["taxon"] == root_entry

    def test_node_without_ott_gets_empty_dict(self):
        # "Foo" has no ottN suffix, so node_get_ott returns None and the
        # entry must be {} regardless of what is in the taxon map.
        t = ete4.Tree("(Foo,B_ott2)Root_ott3;", parser=1)
        taxon_add_prop(t, {1: {"ott": 1}, 2: {"ott": 2}, 3: {"ott": 3}})

        foo = next(n for n in t.traverse() if n.name == "Foo")
        assert foo.props["taxon"] == {}

    def test_unnamed_node_gets_empty_dict(self):
        # An unnamed internal node (e.g. result of resolve_polytomy) has no
        # OTT and must end up with {}.
        t = ete4.Tree("(A_ott1,B_ott2,C_ott4)Root_ott3;", parser=1)
        t.resolve_polytomy()

        taxon_add_prop(t, {1: {"ott": 1}})

        for n in t.traverse():
            if not n.name:
                assert n.props["taxon"] == {}

    def test_unmatched_ott_gets_empty_dict(self):
        # Node has an ottN but it's absent from the map.
        t = ete4.Tree("(A_ott1,B_ott2)Root_ott3;", parser=1)
        taxon_add_prop(t, {99: {"ott": 99}})

        for n in t.traverse():
            assert n.props["taxon"] == {}

    def test_space_separated_ott_in_name_is_matched(self):
        # node_get_ott accepts both "_ottN" and " ottN" suffixes.
        t = ete4.Tree("(A_ott1,B_ott2)Root;", parser=1)
        # Rename a node to use the space-separated form.
        a = next(n for n in t.traverse() if n.name == "A_ott1")
        a.name = "Some name ott1"
        entry = {"ott": 1}
        taxon_add_prop(t, {1: entry})

        assert a.props["taxon"] == entry

    def test_taxon_entry_is_assigned_by_reference(self):
        # The function stores the same dict object on the node, so callers
        # who mutate the taxon map afterwards see the change reflected on
        # the tree (and vice versa).
        t = ete4.Tree("(A_ott1,B_ott2)Root_ott3;", parser=1)
        a_entry = {"ott": 1}
        taxon_add_prop(t, {1: a_entry})

        a = next(n for n in t.traverse() if n.name == "A_ott1")
        assert a.props["taxon"] is a_entry
