# https://etetoolkit.github.io/ete/tutorial/tutorial_trees.html
import collections
import glob
import itertools
import logging
import os
import os.path
import re
import tracemalloc
import time

import ete4

from oz_tree_build.tree_build.oz_tokens import parse_one_zoom_token
from oz_tree_build.tree_build.tree_dating import date_tree

logger = logging.getLogger(__name__)

NWK_PARSER = 1  # Allow internal nodes to also have labels


def apply_node_ages(t, node_ages):
    """
    Apply date properties from node_ages.json to the tree

    Based on tree_loading_oz_ete4:load_metadata by Jonathan Duke
    """

    def median_age(age_dicts, default):
        """Find median in list of [{"age": 123.45}, ..] dicts"""
        if len(age_dicts) == 0:
            return default

        ages = [float(x["age"]) for x in age_dicts]
        midpoint = int((len(ages) - 1) / 2)
        if len(ages) % 2 == 0:
            return (ages[midpoint] + ages[midpoint + 1]) / 2
        return ages[midpoint]

    extract_ott_re = re.compile(r"[_ ](ott\d+)$")

    if not node_ages:
        # No node ages, nothing to do
        return t

    for n in t.traverse():
        # Search for median age either by extracted OTT, or the full node string
        m = extract_ott_re.search(n.name or "")
        n.props["date"] = median_age(
            node_ages.get(m.group(1) if m else n.name, []),
            default=(0 if n.is_leaf and not parse_one_zoom_token(n.name) else None),
        )

        if n.props["date"] is not None and not n.is_leaf and n.props["date"] < 0.000001:
            logging.warning("Interior node %s has median age of 0, setting to None" % n.name)
            n.props["date"] = None


def ages_from_dist(t):
    """
    Apply date properties based on tree dist (branch length)

    Assume leaves have date 0, propogate rest based on dist.

    Based on tree_dating_oz_ete4:compute_dates
    """
    for n in t.traverse("postorder"):
        if n.is_leaf and parse_one_zoom_token(n.name):
            # Leaf node is an inclusion point, force this to have no date
            n.props["date"] = None
            continue

        parent_date = 0  # i.e. default given to leaf nodes

        for c in n.children:
            if c.props["date"] is None or c.dist is None:
                # Propogate missing branch lengths
                parent_date = None
                break
            new_date = c.props["date"] + c.dist
            if new_date > parent_date:
                parent_date = new_date

        n.props["date"] = parent_date


def filter_tree(t, excluded_otts):
    """
    Prune tree (t) of all the otts listed in (excluded_otts)
    """
    if not excluded_otts:
        # Nothing to filter, nothing to do
        return t

    # NB: excluded_otts haven't been parsed to int (no reason to)
    excluded_re = re.compile("|".join("_ott%s$" % ott for ott in excluded_otts))

    def is_leaf_fn(n):
        if n.name and excluded_re.search(n.name):
            n.detach()
            # Don't recurse over nodes we've removed
            return True

        return n.is_leaf

    for _ in t.traverse(strategy="levelorder", is_leaf_fn=is_leaf_fn):
        # NB: We do all the work in the is_leaf_fn, so we can influence whether to recurse
        pass

    return t


def expand_nodes(t, parts_folders, node_ages):
    """
    Recursively resolve OZ inclusion syntax in (t), returning a complete tree.
    """

    def is_leaf_fn(n):
        result = parse_one_zoom_token(n.name, parts_folders)
        if result is None:
            # No inclusion syntax, recurse
            return n.is_leaf

        sub_t = ete4.Tree(result["file"], parser=NWK_PARSER)
        sub_t = filter_tree(sub_t, result.get("excluded_otts"))
        if result["expand_nodes"]:
            sub_t = expand_nodes(sub_t, parts_folders, node_ages)

        # Apply date, either using node_ages for OT trees, or dist for bespoke
        if result["base_ott"]:
            apply_node_ages(sub_t, node_ages)
        else:
            ages_from_dist(sub_t)

        # Replace n with sub_t
        if result["expand_nodes"]:
            n.name = result.get("override_taxon") or sub_t.root.name or result.get("node_name_in_parent")
        else:
            n.name = result.get("node_name_in_parent") or sub_t.root.name
        n.dist = result.get("override_edge_length", sub_t.root.dist)
        n.children = sub_t.root.children

        # Replaced children, no point recursing through the old ones
        return True

    for _ in t.traverse(strategy="levelorder", is_leaf_fn=is_leaf_fn):
        # NB: We do all the work in the is_leaf_fn, so we can influence whether to recurse
        pass

    return t


def main():
    import argparse
    import json
    import sys

    from oz_tree_build.utilities.debug_util import parse_args_and_add_logging_switch

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("treefile", help="The base tree file in newick form")
    parser.add_argument(
        "--nodeages",
        type=str,
        help="The 'node_ages.json' file to parse, if not provided no ages inserted",
    )
    parser.add_argument(
        "outfile",
        nargs="?",
        default="-",
        help="The output tree file path, defaults to stdout",
    )
    args = parse_args_and_add_logging_switch(parser)

    # Work out parts_folders based on treefile location
    parts_folders = dict(
        oz=os.path.dirname(args.treefile),
        ot=os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(args.treefile))),
            "OpenTreeParts",
            "OpenTree_all",
        ),
        ot_required=os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(args.treefile))),
            "OpenTreeParts",
            "OT_required",
        ),
    )

    if args.outfile == "-":
        # NB: None means return string in ete4, so set that and print the return value
        args.outfile = None

    # Load node_ages.json if present
    if args.nodeages:
        with open(args.nodeages, "r") as f:
            node_ages = json.load(f)["node_ages"]
    else:
        node_ages = {}

    write_props = []

    t = ete4.Tree(args.treefile, parser=NWK_PARSER)
    apply_node_ages(
        t, node_ages
    )  # NB: Using node_ages, unlike other bespoke trees. Maybe we should be doing this for all internal trees?
    t = expand_nodes(t, parts_folders, node_ages)

    # If we at least assigned a date to the root, then try to date the tree
    if t.props["date"] is not None:
        date_tree(t)
        write_props.append("date")

    # NB: We need to explicitly list properties we want printing out in [&&NHX:date=x] blocks
    out = t.write(outfile=args.outfile, parser=NWK_PARSER, props=write_props, format_root_node=True)
    if out:
        # ete4 provided some output (so args.outfile was stdout), print it
        print(out)


if __name__ == "__main__":
    main()
