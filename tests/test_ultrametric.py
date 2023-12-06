"""
Unit test for check_ultrametricity and fix_ultrametricity
"""

import dendropy
from oz_tree_build.newick.fix_ultrametricity import fix_ultrametricity
from oz_tree_build.newick.check_ultrametricity import check_ultrametricity


def check_tree_string(tree_string):
    tree = dendropy.Tree.get(data=tree_string, schema="newick")
    return check_ultrametricity(tree)


def test_ultrametric_tree_with_root_length():
    assert check_tree_string("(A:3,(B:2,C:2):1,E:3)D:7;")


def test_ultrametric_tree_without_root_length():
    assert check_tree_string("(A:3,(B:2,C:2):1,E:3)D;")


def test_ultrametric_tree_with_nested_file():
    assert check_tree_string("(A:3,(B:2,C:2):1,E@)D:7;")


def test_ultrametric_tree_with_missing_length():
    assert check_tree_string("(A:3,(B:3,C:3),E:3)D:7;")


def test_non_ultrametric_tree_with_root_length():
    assert not check_tree_string("(A:3,(B:3,C:2):1,E:3)D:7;")


def test_non_ultrametric_tree_with_missing_length():
    assert not check_tree_string("(A:3,(B:2,C:2),E:3)D:7;")


def test_fix_ultrametric_tree():
    tree = dendropy.Tree.get(
        data="(A:3.0,(B:3.0,C:2.0):1.0,E:3.0)D:7.0;", schema="newick"
    )
    fix_ultrametricity(tree, 3, 1)
    assert (
        tree.as_string(schema="newick").strip()
        == "(A:3.0,(B:2.0,C:2.0):1.0,E:3.0)D:7.0;"
    )
