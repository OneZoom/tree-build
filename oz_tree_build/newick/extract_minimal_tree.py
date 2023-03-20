'''
Extract a minimal tree that includes a set of taxa
'''

import argparse
import logging
import sys
from typing import Set

from oz_tree_build.newick.newick_parser import parse_tree

__author__ = "David Ebbo"

def extract_minimal_tree(newick_tree, target_taxa: Set[str]):
    # We build the node list as we find them and process them
    node_list = []

    # Clone the taxa set so we don't modify the original
    target_taxa = set(target_taxa)

    for node in parse_tree(newick_tree):
        taxon = node['taxon']
        ott = node['ott']
        node_start_index = node['start']
        node_end_index = node['end']

        # This is a bit hacky. Ideally, the parser would give us the child count
        is_parent_node = newick_tree[node_start_index] == '('

        if taxon in target_taxa or ott in target_taxa:
            # We've found a target taxon, so remove it from the target list
            target_taxa.remove(taxon if taxon in target_taxa else ott)
            found_target_taxon = True
        else:
            found_target_taxon = False

        # If this taxon is in the target list, add it to the nodes list
        if found_target_taxon or is_parent_node:
            # Any node with higher depth must be a child of this one
            # But ignore the whole child logic if we're separating trees
            children = [n for n in node_list if n["depth"] > node["depth"]]

            # Assert that all the children have depth 1 less than this node. This is
            # because any deeper nodes would have been bubbled up 
            assert all([child_node["depth"] == node['depth'] + 1 for child_node in children])

            # Reduce the depth of the children to bubble them up
            for child_node in children:
                child_node["depth"] -= 1

            # If we found a taxon, or there are multiple children, we need to add a node to the list
            if found_target_taxon or len(children) > 1:
                # Remove the children from the search list
                node_list = [n for n in node_list if n not in children]

                # Full name including the edge length
                tree_string = newick_tree[node['full_name_start_index']:node_end_index]
                if children:
                    # Add the children to the tree string
                    tree_string = f"({','.join([child_node['tree_string'] for child_node in children])}){tree_string}"

                node_list.append({"name": taxon, "ott": ott, "tree_string": tree_string, "depth": node["depth"]})

        # If we've found all the target taxa, we're done
        if not target_taxa and len(node_list) <= 1:
            break

    if target_taxa:
        logging.warning(f'Could not find the following taxa: {", ".join(target_taxa)}')

    # Return the tree, if any
    assert len(node_list) <= 1
    return node_list[0]['tree_string'] if len(node_list) > 0 else None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('treefile', type=argparse.FileType('r'), nargs='?', default=sys.stdin, help='The tree file in newick form')
    parser.add_argument('outfile', type=argparse.FileType('w'), nargs='?', default=sys.stdout, help='The output tree file')
    parser.add_argument('--taxa', '-t', nargs='+', required=True, help='the taxa to search for')
    args = parser.parse_args()

    target_taxa = set(args.taxa)

    # Read the whole file as a string. This is not ideal, but it's still
    # very fast even with the full OpenTree tree.
    # This could be optimized to read by chunks, with more complexity
    tree = args.treefile.read()

    result = extract_minimal_tree(tree, target_taxa)
    if result:
        args.outfile.write(result + ';\n')

if __name__ == '__main__':
    main()