'''
Extract one or more subtrees from a Newick tree, including support for excluded taxa.
'''

'''
Everything is processed in a single pass over the tree string, using the newick_parser module.
As we walk through the nodes, we process both the target taxa and the excluded taxa.

From the command line, run for example:
python3 extract_trees.py tree.tre -t Tupaia Camelidae
'''


import argparse
import logging
import sys
from typing import Set

from oz_tree_build.newick.newick_parser import parse_tree

__author__ = "David Ebbo"

def extract_trees(newick_tree, target_taxa: Set[str], excluded_taxa: Set[str] = {}):
    # We build the subtrees and exclusion lists as we find them and process them
    subtrees = []
    excluded_ranges = []

    # Clone the taxa set so we don't modify the original
    target_taxa = set(target_taxa)

    for node in parse_tree(newick_tree):
        taxon = node['taxon']
        ott = node['ott']
        node_start_index = node['start']
        node_end_index = node['end']

        # If this taxon or ott is in the excluded list, add it to the excluded ranges
        if taxon in excluded_taxa or ott in excluded_taxa:
            # Use different logic depending on comma position
            if newick_tree[node_start_index-1] == ',':
                # Exclude the comma before the excluded taxon. e.g. (A,B,REMOVE_ME) --> (A,B)
                excluded_range = (node_start_index-1, node_end_index)
            elif newick_tree[node_end_index] == ',':
                # Exclude the comma after the excluded taxon. e.g. (REMOVE_ME,B,C) --> (B,C)
                excluded_range = (node_start_index, node_end_index+1)
            else:
                # Otherwise just exclude the taxon, e.g. (REMOVE_ME) --> ()
                # This can lead to empty brackets, but that's harmless enough
                excluded_range = (node_start_index, node_end_index)
            excluded_ranges.append(excluded_range)
            # Sort the excluded ranges by start index. Not efficient, but not on critical path
            excluded_ranges.sort(key=lambda x: x[0])

        # If this taxon or ott is in the target list, add it to the nodes list
        if taxon in target_taxa or ott in target_taxa:
            # First, remove it from the target list
            target_taxa.remove(taxon if taxon in target_taxa else ott)

            tree_string = ""

            def string_to_append(start, end):
                # Fix up situation that would end up generating "(,"
                if tree_string and tree_string[-1] == '(' and newick_tree[start] == ',':
                    start += 1
                return newick_tree[start:end]

            # Extract the subtree for this node, skipping over excluded ranges
            prev_range = (node_start_index, node_start_index)
            for range in excluded_ranges:
                # Only process ranges that are strictly inside the current taxon
                if range[0] > node_start_index and range[0] < node_end_index and range[1] > prev_range[1]:
                    tree_string += string_to_append(prev_range[1], range[0])
                    prev_range = range
            tree_string += string_to_append(prev_range[1], node_end_index)

            subtrees.append({"name": taxon, "ott": ott, "tree_string": tree_string})

        # If we've found all the target taxa, we're done
        if not target_taxa:
            break

    if target_taxa:
        logging.warning(f'Could not find the following taxa: {", ".join(target_taxa)}')

    # Return a dictionary of subtrees, indexed by ott or name
    return {subtree['ott'] or subtree['name']: subtree['tree_string'] for subtree in subtrees}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('treefile', type=argparse.FileType('r'), nargs='?', default=sys.stdin, help='The tree file in newick form')
    parser.add_argument('outfile', type=argparse.FileType('w'), nargs='?', default=sys.stdout, help='The output tree file')
    parser.add_argument('--taxa', '-t', nargs='+', required=True, help='the taxon to search for')
    parser.add_argument('--excluded_taxa', '-x', nargs='+', help='taxa to exclude from the result')
    args = parser.parse_args()

    target_taxa = set(args.taxa)
    excluded_taxa = set(args.excluded_taxa) if args.excluded_taxa else set()

    # Read the whole file as a string. This is not ideal, but it's still very fast
    # even with the full OpenTree tree, and the memory usage is acceptable.
    # This could be optimized to read by chunks, with much more complexity.
    tree = args.treefile.read()

    result = extract_trees(tree, target_taxa, excluded_taxa)

    if len(result) == 1:
        # If only one result, just output the tree
        args.outfile.write(f'{next(iter(result.values()))};\n')
    else:
        # If multiple items, output each on a separate line, prefixed with the name/ott
        for name, tree in result.items():
            args.outfile.write(f'{name}: {tree};\n')

if __name__ == '__main__':
    main()