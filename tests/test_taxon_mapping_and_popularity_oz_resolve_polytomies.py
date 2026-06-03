"""Tests for oz_tree_build.taxon_mapping_and_popularity.dendropy_extras.oz_resolve_polytomies

Confirms that resolving polytomies preserves the `age` attribute on existing nodes,
and that each newly-inserted internal node is given an age equal to its enclosing
polytomy parent's age plus a zero-length branch -- so the tree remains
internally consistent (parent.age - child.age == child.edge.length everywhere).
"""

import dendropy
import pytest

from oz_tree_build.taxon_mapping_and_popularity.dendropy_extras import (
    group_genera_in_polytomies,
    oz_resolve_polytomies,
)

# oz_resolve_polytomies calls tree.group_genera_in_polytomies() internally, so
# the same monkey patch that CSV_base_table_creator does at runtime is needed here.
dendropy.Tree.group_genera_in_polytomies = group_genera_in_polytomies


def build_dated_tree(nwk):
    """Parse Newick and tag every node with a `data` dict + an ultrametric `age`.

    `data` is the marker oz_resolve_polytomies uses to tell pre-existing nodes
    apart from inserted ones. Ages are computed bottom-up assuming leaves at 0.
    """
    t = dendropy.Tree.get(
        data=nwk,
        schema="newick",
        suppress_leaf_node_taxa=True,
        suppress_internal_node_taxa=True,
    )
    for node in t.preorder_node_iter():
        node.data = {}
    for node in t.postorder_node_iter():
        if node.is_leaf():
            node.age = 0.0
        else:
            child = next(node.child_node_iter())
            node.age = child.age + (child.edge.length or 0.0)
    return t


def existing_ids(tree):
    return {id(n) for n in tree.preorder_node_iter()}


def new_nodes(tree, existing):
    return [n for n in tree.preorder_node_iter() if id(n) not in existing]


def assert_internally_consistent(tree):
    """For every parent-child edge: parent.age == child.age + child.edge.length."""
    for node in tree.preorder_node_iter():
        if node.parent_node is None:
            continue
        assert node.edge.length is not None, f"node {node.label!r} has no edge.length"
        expected = node.parent_node.age - node.age
        assert node.edge.length == pytest.approx(expected), (
            f"inconsistent at {node.label!r}: parent.age={node.parent_node.age}, "
            f"age={node.age}, edge.length={node.edge.length}"
        )


def test_binary_tree_has_no_new_nodes():
    """Fully bifurcating tree is untouched: no new nodes, no mutated ages."""
    t = build_dated_tree("((a:1,b:1)x:2,c:3)root;")
    existing = existing_ids(t)
    snapshot = {id(n): n.age for n in t.preorder_node_iter()}

    n_new = oz_resolve_polytomies(t, seed=0)

    assert n_new == 0
    assert new_nodes(t, existing) == []
    for n in t.preorder_node_iter():
        assert n.age == snapshot[id(n)]
    assert_internally_consistent(t)


def test_three_way_polytomy_adds_one_node_at_parent_age():
    """3-leaf polytomy => 1 new internal node, sitting at the polytomy parent's age."""
    t = build_dated_tree("(a:5,b:5,c:5)root;")
    existing = existing_ids(t)

    n_new = oz_resolve_polytomies(t, seed=0)

    inserted = new_nodes(t, existing)
    assert n_new == 1
    assert len(inserted) == 1
    assert inserted[0].age == 5.0
    assert inserted[0].edge.length == 0
    assert_internally_consistent(t)


def test_large_polytomy_inserts_chain_all_at_parent_age():
    """5-leaf polytomy inserts (5-2)=3 internal nodes, all at the same time as the parent.

    Exercises the preorder traversal: inner inserted nodes must see their newly-
    inserted parent's age, which was set on the same pass.
    """
    t = build_dated_tree("(a:7,b:7,c:7,d:7,e:7)root;")
    existing = existing_ids(t)

    n_new = oz_resolve_polytomies(t, seed=0)

    inserted = new_nodes(t, existing)
    assert n_new == 3
    assert len(inserted) == 3
    for nn in inserted:
        assert nn.age == 7.0, f"inserted node has wrong age: {nn.age}"
        assert nn.edge.length == 0
    assert_internally_consistent(t)


def test_polytomy_of_dated_subtrees_preserves_children():
    """Polytomy whose children are dated subtrees: subtree ages/edges are untouched."""
    t = build_dated_tree("((a:2,b:2)x:6,(c:3,d:3)y:5,e:8)root;")
    existing = existing_ids(t)
    pre = {n.label: (n.age, n.edge.length if n.parent_node else None) for n in t.preorder_node_iter() if n.label}

    n_new = oz_resolve_polytomies(t, seed=0)

    assert n_new == 1  # root is a 3-way polytomy
    for n in t.preorder_node_iter():
        if n.label and n.label in pre:
            age, edge = pre[n.label]
            assert n.age == age, f"existing age mutated on {n.label!r}"
            if edge is not None:
                assert n.edge.length == edge, f"existing edge mutated on {n.label!r}"
    for nn in new_nodes(t, existing):
        assert nn.age == 8.0
        assert nn.edge.length == 0
    assert_internally_consistent(t)


def test_multiple_polytomies_at_different_depths():
    """Two polytomies at different ages each propagate their own parent's age."""
    t = build_dated_tree("((a:1,b:1,c:1)x:9,(d:2,e:2,f:2,g:2)y:8)root;")
    existing = existing_ids(t)
    by_label = {n.label: n for n in t.preorder_node_iter() if n.label}
    # fixture sanity
    assert by_label["x"].age == 1.0
    assert by_label["y"].age == 2.0

    n_new = oz_resolve_polytomies(t, seed=0)

    # x is a 3-way polytomy (1 new node); y is 4-way (2 new nodes).
    assert n_new == 3
    for nn in new_nodes(t, existing):
        # The first existing ancestor is the polytomy parent (x or y).
        anc = nn.parent_node
        while id(anc) not in existing:
            anc = anc.parent_node
        assert nn.age == anc.age
        assert nn.edge.length == 0
    assert_internally_consistent(t)


def test_existing_nodes_are_not_mutated():
    """oz_resolve_polytomies must not touch existing nodes' age or edge.length."""
    t = build_dated_tree("(a:5,b:5,c:5,d:5)root;")
    snapshot = {id(n): (n.age, n.edge.length if n.parent_node else None) for n in t.preorder_node_iter()}

    oz_resolve_polytomies(t, seed=0)

    for n in t.preorder_node_iter():
        if id(n) in snapshot:
            age, edge = snapshot[id(n)]
            assert n.age == age, f"existing age mutated: {n.label!r}"
            if edge is not None:
                assert n.edge.length == edge, f"existing edge mutated: {n.label!r}"


def test_missing_parent_age_leaves_new_node_ageless():
    """No ages anywhere => new node gets edge.length=0 but no age is invented."""
    t = dendropy.Tree.get(
        data="(a,b,c)root;",
        schema="newick",
        suppress_leaf_node_taxa=True,
        suppress_internal_node_taxa=True,
    )
    for node in t.preorder_node_iter():
        node.data = {}
    existing = existing_ids(t)

    n_new = oz_resolve_polytomies(t, seed=0)

    inserted = new_nodes(t, existing)
    assert n_new == 1
    assert len(inserted) == 1
    assert inserted[0].edge.length == 0
    # DendroPy initialises Node.age to None; the function must not invent an age
    # when the polytomy parent has none.
    assert inserted[0].age is None, "no parent age means no propagated age"


def test_resolution_is_deterministic_for_same_seed():
    """Same input + seed produces byte-identical Newick output."""
    t1 = build_dated_tree("(a:5,b:5,c:5,d:5,e:5)root;")
    t2 = build_dated_tree("(a:5,b:5,c:5,d:5,e:5)root;")

    oz_resolve_polytomies(t1, seed=42)
    oz_resolve_polytomies(t2, seed=42)

    assert t1.as_string(schema="newick") == t2.as_string(schema="newick")
