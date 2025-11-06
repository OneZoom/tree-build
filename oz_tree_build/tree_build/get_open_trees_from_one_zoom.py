"""
Create subtrees from the OpenTree, on the basis of ott numbers in a set of newick files.

Usage: getOpenTreesFromOneZoom.py OpenTreeFile.tre output_dir file1.PHY file2.PHY ...

This script places a set of inclusion files into output_dir, based on the names of nodes
in the input .PHY files. The input files should contain one or more node names in the OneZoom
@include format which is the scientific name + '_ott' + (an OTT id, optionally a ~ sign, and
optionally other OTT numbers separated by an minus sign) + '@', e.g. Brachiopoda_ott826261@
This specifies that the node should be replaced with part of the OpenTree: namely the subtree
starting at ott node 826261.

E.g.
    foobar_ott123@
        create a node named foobar with ott 123, consisting of all descendants of
        ott 123 in the opentree.

    foobar_ott123~456-789-111@
        create a node named foobar with ott 123, using ott456 minus the descendant
        subtrees with ott 789 and 111 (the tilde sign can be read an a equals, used
        as Dendropy doesn't like equals signs in taxon names.

    foobar_ott123~-789-111@
        shorthand for foobar_ott123~123-789-111@

    foobar_ott~456-789-111@
        create a node named foobar without any OTT number,
        using ott456 minus the descendant subtrees 789 and 111

The actual inclusion is done by the build_oz_tree.py. This script merely creates the
files to include. It does this by extracting the relevant subtree from the full OpenTree
"""

import argparse
import logging
import os
import sys
import time

from ..newick.extract_trees import extract_trees
from .oz_tokens import enumerate_one_zoom_tokens

__author__ = "David Ebbo"


def get_inclusions_and_exclusions_from_one_zoom_file(file, all_included_otts, all_excluded_otts):
    """
    Find all the included and excluded ott numbers in a OneZoom files & add them to the sets
    """

    with open(file, encoding="utf8") as stream:
        tree = stream.read()

    for result in enumerate_one_zoom_tokens(tree):
        # Check if the result has a base ott (won't have it if it's inserting another OZ file)
        if result.get("base_ott") is not None:
            all_included_otts.add(result["base_ott"])
            all_excluded_otts.update(result["excluded_otts"])


def extract_trees_from_open_tree_file(open_tree_file, output_dir, all_included_otts, all_excluded_otts):
    """
    Extract the subtrees from the Open Tree file, based on the list of included/excluded otts
    """

    # Read the contents of the open tree file into a string
    with open(open_tree_file, encoding="utf8") as f:
        fulltree = f.read()

    trees = extract_trees(fulltree, all_included_otts, excluded_taxa=all_excluded_otts)

    logging.info(f"Extracted {len(trees)} trees from Open Tree file")

    # Save each tree to a file named after the taxon
    for ott, tree in trees.items():
        file = os.path.join(output_dir, ott + ".phy")
        logging.debug(f"Writing file: {file}")
        with open(file, "w", encoding="utf8") as f:
            f.write(tree)
            f.write(";\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--verbosity",
        "-v",
        action="count",
        default=0,
        help="verbosity level: output extra non-essential info",
    )
    parser.add_argument("open_tree_file", help="Path to the Open Tree newick file")
    parser.add_argument(
        "output_dir",
        help="Path to the directory in which to save the OpenTree subtrees",
    )
    parser.add_argument(
        "parse_files",
        nargs="+",
        help="A list of newick files to parse for OTT numbers, giving the subtrees to extract",
    )
    args = parser.parse_args()

    if args.verbosity == 0:
        logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    elif args.verbosity == 1:
        logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    elif args.verbosity == 2:
        logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

    start = time.time()
    if not os.path.isfile(args.open_tree_file):
        logging.warning(f"Could not find the OpenTree file {args.open_tree_file}")

    # Go through all the OneZoom files, and gather all the ott numbers to include and exclude.
    # NB: excluded ott numbers don't need to be specifically given an included ott number
    included_otts = set()
    excluded_otts = set()
    for file in args.parse_files:
        logging.info(f"== Processing One Zoom file {file}")
        get_inclusions_and_exclusions_from_one_zoom_file(file, included_otts, excluded_otts)

    extract_trees_from_open_tree_file(args.open_tree_file, args.output_dir, included_otts, excluded_otts)

    end = time.time()
    logging.debug(f"Time taken: {end - start} seconds")


if __name__ == "__main__":
    main()
