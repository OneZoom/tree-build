"""
Unit test for check_ultrametricity and fix_ultrametricity
"""

import dendropy

from oz_tree_build.newick.check_ultrametricity import check_ultrametricity
from oz_tree_build.newick.fix_ultrametricity import fix_ultrametricity


def check_tree_string(tree_string):
    tree = dendropy.Tree.get(data=tree_string, schema="newick")
    return check_ultrametricity(tree)


def test_ultrametric_tree_with_root_length():
    assert check_tree_string("(A:3,(B:2,C:2):1,E:3)D:7;")


def test_ultrametric_tree_without_root_length():
    assert check_tree_string("(A:3,(B:2,C:2):1,E:3)D;")


def test_ultrametric_tree_with_nested_file():
    assert check_tree_string("(A:3,(B:2,C:2):1,E@)D:7;")


def test_ultrametric_tree_with_missing_interior_length():
    assert check_tree_string("(A:3,(B:3,C:3),E:3)D:7;")


def test_ultrametric_tree_with_missing_leaf_length():
    assert check_tree_string("(A:3,(B:2,C):1,E:3)D:7;")


def test_non_ultrametric_tree_with_root_length():
    assert not check_tree_string("(A:3,(B:3,C:2):1,E:3)D:7;")


def test_non_ultrametric_tree_with_missing_length():
    assert not check_tree_string("(A:3,(B:2,C:2),E:3)D:7;")


def check_fix_ultrametric_tree(
    tree_string, expected_length, max_adjustment, expected_tree_string
):
    tree = dendropy.Tree.get(data=tree_string, schema="newick")
    fix_ultrametricity(tree, expected_length, max_adjustment)
    assert tree.as_string(schema="newick").strip() == expected_tree_string


def test_fix_ultrametric_tree():
    check_fix_ultrametric_tree(
        "(A:3.0,(B:3.0,C:2.0):1.0,E:3.0)D:7.0;",
        3,
        1,
        "(A:3.0,(B:2.0,C:2.0):1.0,E:3.0)D:7.0;",
    )


def test_fix_ultrametric_tree_no_leaf_length():
    check_fix_ultrametric_tree(
        "(A:3.0,(B:3.0,C:2.0):1.0,E)D:7.0;",
        3,
        1,
        "(A:3.0,(B:2.0,C:2.0):1.0,E)D:7.0;",
    )
