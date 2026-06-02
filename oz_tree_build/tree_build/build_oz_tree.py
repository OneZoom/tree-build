# https://etetoolkit.github.io/ete/tutorial/tutorial_trees.html
import argparse
import json
import logging
import os
import os.path
import re

import ete4
import ete4.parser.newick

from oz_tree_build.tree_build.infer_ages import infer_ages
from oz_tree_build.tree_build.oz_tokens import parse_one_zoom_token
from oz_tree_build.tree_build.tree_dating import date_tree

from ..utilities.debug_util import parse_args_and_add_logging_switch

logger = logging.getLogger(__name__)

# Custom parser, force { to be quoted for DendroPy
NAME = {
    "pname": "name",
    "read": ete4.parser.newick.unquote,
    "write": lambda name: ete4.parser.newick.quote(name, escaped_chars=" \t\r\n()[]':;,{}="),
}
DIST = {"pname": "dist", "read": float, "write": lambda x: f"{float(x):g}"}
NWK_WRITE_PARSER = {
    "leaf": [NAME, DIST],
    "internal": [NAME, DIST],
}
# NB: We can't use a custom parser when reading, due to a bug in ete4: https://github.com/etetoolkit/ete/issues/801
NWK_READ_PARSER = 1


def filter_tree(t, excluded_otts):
    """
    Prune tree (t) of all the otts listed in (excluded_otts)
    """
    if not excluded_otts:
        # Nothing to filter, nothing to do
        return t

    # NB: excluded_otts haven't been parsed to int (no reason to)
    excluded_re = re.compile("|".join(f"_ott{ott}$" for ott in excluded_otts))

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

        # If file not present, ditch inclusion syntax and carry on
        if not os.path.exists(result["file"]):
            logger.warning(f"Subtree file {result['file']} does not exist")
            n.name = result["node_name_in_parent"]
            return n.is_leaf

        sub_t = ete4.Tree(result["file"], parser=NWK_READ_PARSER)
        sub_t = filter_tree(sub_t, result.get("excluded_otts"))
        if result["expand_nodes"]:
            sub_t = expand_nodes(sub_t, parts_folders, node_ages)

        # Fill in props['date'], working from leaves backwards or node_ages
        infer_ages(sub_t, node_ages)

        # Replace n with sub_t
        if result["expand_nodes"]:
            n.name = result.get("override_taxon") or sub_t.root.name or result.get("node_name_in_parent")
        else:
            n.name = result.get("node_name_in_parent") or sub_t.root.name
        n.dist = result.get("override_edge_length", sub_t.root.dist)
        n.props["date"] = sub_t.root.props.get("date")
        n.children = sub_t.root.children

        # Replaced children, no point recursing through the old ones
        return True

    for _ in t.traverse(strategy="levelorder", is_leaf_fn=is_leaf_fn):
        # NB: We do all the work in the is_leaf_fn, so we can influence whether to recurse
        pass

    return t


def main():
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
        with open(args.nodeages) as f:
            node_ages = json.load(f)["node_ages"]
    else:
        node_ages = {}

    write_props = []

    t = ete4.Tree(args.treefile, parser=NWK_READ_PARSER)
    infer_ages(t, node_ages)
    t = expand_nodes(t, parts_folders, node_ages)

    # If we at least assigned a date to the root, then try to date the tree
    t.root.props["date"] = 4566.9  # Hadean starts 4567 Mya ago, bodge it
    if t.props.get("date") is not None:
        date_tree(t)
        write_props.append("date")

    # NB: We need to explicitly list properties we want printing out in [&&NHX:date=x] blocks
    out = t.write(outfile=args.outfile, parser=NWK_WRITE_PARSER, props=write_props, format_root_node=True)
    if out:
        # ete4 provided some output (so args.outfile was stdout), print it
        print(out)


if __name__ == "__main__":
    main()
