"""
Unit tests for apply_mask_to_object_graph()
"""

import copy
from oz_tree_build.utilities.apply_mask_to_object_graph import (
    apply_mask_to_object_graph,
    KEEP,
)


def run_test(obj, mask, expected):
    # Clone the object so we don't modify it
    obj = copy.deepcopy(obj)

    apply_mask_to_object_graph(obj, mask)
    assert obj == expected, f"Expected {expected}, got {obj}"


def test_simple_objects():
    run_test({"a": 1, "b": 2}, {"a": KEEP}, {"a": 1})
    run_test({"a": 1, "b": 2}, {"b": KEEP}, {"b": 2})
    run_test({"a": 1, "b": 2}, {"c": KEEP}, {})
    run_test({"a": 1, "b": 2}, {"a": KEEP, "b": KEEP}, {"a": 1, "b": 2})
    run_test({"a": 1, "b": 2}, {"a": KEEP, "c": KEEP}, {"a": 1})
    run_test({"a": 1, "b": 2}, {"c": KEEP, "b": KEEP}, {"b": 2})


def test_complex_objects():
    o = {
        "a": {
            "b": 1,
            "c": [{"d": 2, "e": "foo"}, {"d": 2, "e": "bar"}, {"d": 2, "e": "baz"}],
        },
        "f": {"g": 3, "h": []},
    }

    run_test(o, {"f": {"g": KEEP}}, {"f": {"g": 3}})
    run_test(o, {"a": {"b": KEEP}, "f": {"g": KEEP}}, {"a": {"b": 1}, "f": {"g": 3}})
    run_test(
        o,
        {"a": {"c": [{"e": KEEP}]}},
        {"a": {"c": [{"e": "foo"}, {"e": "bar"}, {"e": "baz"}]}},
    )
    run_test(
        o, {"a": {"c": [{"d": KEEP}]}}, {"a": {"c": [{"d": 2}, {"d": 2}, {"d": 2}]}}
    )
    run_test(o, {"f": {"h": KEEP}}, {"f": {"h": []}})
