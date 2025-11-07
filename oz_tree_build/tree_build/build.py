# https://etetoolkit.github.io/ete/tutorial/tutorial_trees.html
import collections
import glob
import itertools
import os
import os.path
import re
import tracemalloc
import time

import ete4

from oz_tree_build.tree_build.oz_tokens import parse_one_zoom_token

NWK_PARSER = 1  # Allow internal nodes to also have labels




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


def expand_nodes(t, parts_folders):
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
            sub_t = expand_nodes(sub_t, parts_folders)

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
    import sys
    from oz_tree_build.utilities.debug_util import parse_args_and_add_logging_switch

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("treefile", help="The base tree file in newick form")
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

    t = ete4.Tree(args.treefile, parser=NWK_PARSER)
    t = expand_nodes(t, parts_folders)
    # NB: We need to explicitly list properties we want printing out in [&&NHX:date=x] blocks
    out = t.write(outfile=args.outfile, parser=NWK_PARSER, props=["date"], format_root_node=True)
    if out:
        # ete4 provided some output (so args.outfile was stdout), print it
        print(out)


if __name__ == "__main__":
    main()
