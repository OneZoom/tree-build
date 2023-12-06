"""
Unit test for check_ultrametricity
"""

import dendropy
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
