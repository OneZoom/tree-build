"""
Extract one or more subtrees from a Newick tree, including support for excluded taxa.

Everything is processed in one pass over the tree string, using the newick_parser module.
As we walk through the nodes, we process both the target taxa and the excluded taxa.

It also supports including a number of ancestors for each target taxon found.
This can give useful context around the target taxon.

From the command line, run for example:
.venv/bin/extract_trees tree.tre -t Tupaia Camelidae
"""

import argparse
import logging
import sys
from typing import Set

from .newick_parser import parse_tree

__author__ = "David Ebbo"


def str_to_append(newick_tree, tree_string, start, end):
    # Fix up situation that would end up generating "(,"
    if tree_string and tree_string[-1] == "(" and newick_tree[start] == ",":
        start += 1
    return newick_tree[start:end]


def extract_trees(
    newick_tree,
    target_taxa: Set[str],
    excluded_taxa=None,
    included_ancestor_count=0,
):
    # We build the subtrees and exclusion lists as we find them and process them
    if excluded_taxa is None:
        excluded_taxa = set()
    subtrees = []
    excluded_ranges = []

    # Clone the taxa set so we don't modify the original
    target_taxa = set(target_taxa)

    # Keep track of how many ancestors we still need to find among all the subtrees. This
    # is an optimization to avoid processing the whole tree once we've found everything
    overall_ancestor_needed = 0

    for node in parse_tree(newick_tree):
        taxon = node["taxon"]
        ott = node["ott"]
        node_start_idx = node["start"]
        node_end_idx = node["end"]

        # Of any subtree that needs ancestors, add the current taxon if it's an ancestor
        if overall_ancestor_needed:
            for subtree in subtrees:
                if subtree["ancestors_needed"] and node_start_idx < subtree["start"]:
                    subtree["tree_string"] = "(" + subtree["tree_string"] + ")" + taxon
                    subtree["ancestors_needed"] -= 1
                    overall_ancestor_needed -= 1

        # If this taxon or ott is in the excluded list, add it to the excluded ranges
        if taxon in excluded_taxa or ott in excluded_taxa:
            # Use different logic depending on comma position
            if newick_tree[node_start_idx - 1] == ",":
                # Exclude comma before the excluded taxon. e.g. (A,B,REMOVE_ME) --> (A,B)
                excluded_range = (node_start_idx - 1, node_end_idx)
            elif newick_tree[node_end_idx] == ",":
                # Exclude  comma after the excluded taxon. e.g. (REMOVE_ME,B,C) --> (B,C)
                excluded_range = (node_start_idx, node_end_idx + 1)
            else:
                # Otherwise just exclude the taxon, e.g. (REMOVE_ME) --> ()
                # This can lead to empty brackets, but that's harmless enough
                excluded_range = (node_start_idx, node_end_idx)
            excluded_ranges.append(excluded_range)
            # Sort excluded ranges by start index. Not efficient but not on critical path
            excluded_ranges.sort(key=lambda x: x[0])

        # If this taxon or ott is in the target list, add it to the nodes list
        if taxon in target_taxa or ott in target_taxa:
            # First, remove it from the target list
            target_taxa.remove(taxon if taxon in target_taxa else ott)

            tree_str = ""

            # Extract the subtree for this node, skipping over excluded ranges
            prev_r = (node_start_idx, node_start_idx)
            for r in excluded_ranges:
                # Only process ranges that are strictly inside the current taxon
                if r[0] > node_start_idx and r[0] < node_end_idx and r[1] > prev_r[1]:
                    tree_str += str_to_append(newick_tree, tree_str, prev_r[1], r[0])
                    prev_r = r
            tree_str += str_to_append(newick_tree, tree_str, prev_r[1], node_end_idx)

            subtrees.append(
                {
                    "name": taxon,
                    "ott": ott,
                    "tree_string": tree_str,
                    "start": node_start_idx,
                    "ancestors_needed": included_ancestor_count,
                }
            )
            overall_ancestor_needed += included_ancestor_count

        # If we've found all the target taxa and ancestors, we're done
        if not target_taxa and not overall_ancestor_needed:
            break

    if target_taxa:
        logging.warning(f'Could not find the following taxa: {", ".join(target_taxa)}')

    # Return a dictionary of subtrees, indexed by ott or name
    return {
        subtree["ott"] or subtree["name"]: subtree["tree_string"]
        for subtree in subtrees
    }


"""
Extract a single subtree from a Newick file, given a taxon name or ott id
"""


def get_taxon_subtree_from_newick_file(newick_tree_file, taxon):
    with open(newick_tree_file) as f:
        tree = f.read()

    subtrees = extract_trees(tree, {taxon})

    if len(subtrees) == 0:
        raise Exception(f"No subtree found for taxon {taxon}")

    return next(iter(subtrees.values())) + ";"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "treefile",
        type=argparse.FileType("r"),
        nargs="?",
        default=sys.stdin,
        help="The tree file in newick form",
    )
    parser.add_argument(
        "outfile",
        type=argparse.FileType("w"),
        nargs="?",
        default=sys.stdout,
        help="The output tree file",
    )
    parser.add_argument(
        "--taxa", "-t", nargs="+", required=True, help="the taxon to search for"
    )
    parser.add_argument(
        "--excluded_taxa", "-x", nargs="+", help="taxa to exclude from the result"
    )
    parser.add_argument(
        "--included_ancestors",
        "-a",
        type=int,
        default=0,
        help="number of included ancestors for each taxon found",
    )
    args = parser.parse_args()

    target_taxa = set(args.taxa)
    excluded_taxa = set(args.excluded_taxa) if args.excluded_taxa else set()

    # Read the whole file as a string. This is not ideal, but it's still very fast
    # even with the full OpenTree tree, and the memory usage is acceptable.
    # This could be optimized to read by chunks, with much more complexity.
    tree = args.treefile.read()

    result = extract_trees(tree, target_taxa, excluded_taxa, args.included_ancestors)

    if len(result) == 1:
        # If only one result, just output the tree
        args.outfile.write(f"{next(iter(result.values()))};\n")
    else:
        # If multiple items, output each on a separate line, prefixed with the name/ott
        for name, tree in result.items():
            args.outfile.write(f"{name}: {tree};\n")


if __name__ == "__main__":
    main()
