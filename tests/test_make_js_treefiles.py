"""
Unit tests for make_js_treefiles
"""

from oz_tree_build.utilities import make_js_treefiles


def test_generate_completetree_js():
    assert (
        make_js_treefiles.generate_completetree_js("(())")
        == """
var rawData = '(())';
    """.strip()
    )
    assert (
        make_js_treefiles.generate_completetree_js("((()()))")
        == """
var rawData = '((()()))';
    """.strip()
    )
