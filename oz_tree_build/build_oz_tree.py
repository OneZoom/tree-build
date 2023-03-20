#!/usr/bin/env python3
'''
Build the entire OneZoom tree from the saved parts.

It does this in one pass, by starting with the base file (e.g. base.PHY) and
recursively expanding any OneZoom tokens it finds.
'''

import argparse
import logging
import os
import sys

from oz_tree_build.oz_tokens import enumerate_one_zoom_tokens
from oz_tree_build.token_to_oz_tree_file_mapping import token_to_file_map

__author__ = "David Ebbo"

def trim_tree(tree):
    # Skip the comment block at the start of the file, if any
    if '[' in tree:
        tree = tree[tree.index(']')+1:]

    # Trim any whitespace
    tree = tree.strip()

    # Strip the trailing semicolon
    if tree[-1] == ';':
        tree = tree[:-1]

    return tree
    
'''
Copy the input file to the output file, recursively expanding any OneZoom tokens
'''
def build_oz_tree(base_file, ot_parts_folder, output_stream):
    def process_newick(file, node_name_in_parent=None, edge_length_in_parent=None,
                       mapping_entry=None, expand_nodes=False):
        logging.debug(f'Processing {file}')

        if not os.path.exists(file):
            logging.warning(f"Subtree file {file} does not exist")
            return False

        with open(file, 'r', encoding="utf8") as stream:
            tree = stream.read()

        tree = trim_tree(tree)
        index = 0

        # We only need to look for children if it's a OneZoom file (i.e. .PHY extension)
        if expand_nodes:
            for result in enumerate_one_zoom_tokens(tree):
                # Write the part of the tree before the child
                output_stream.write(tree[index:result['start']])

                child_full_name = result["full_name"]

                # Check if OneZoom token has a base ott (e.g. 123 in foobar_ott123~456-789-111)
                if 'base_ott' in result:
                    # It's an extracted Open Tree file, e.g. 123.phy
                    sub_file = os.path.join(ot_parts_folder, f'{result["base_ott"]}.phy')
                    if not os.path.exists(sub_file):
                        # Fall back to .nwk, which happens for additional copied files
                        sub_file = os.path.join(ot_parts_folder, f'{result["base_ott"]}.nwk')
                    expand_child_nodes = False
                    child_mapping_entry = None
                else:
                    # Otherwise, it's a OneZoom file, e.g. AMORPHEA@ --> Amorphea.PHY
                    child_mapping_entry = token_to_file_map[child_full_name]
                    sub_file = os.path.join(oz_parts_folder, child_mapping_entry['file'])
                    expand_child_nodes = True

                if process_newick(sub_file, child_full_name, result['edge_length'], child_mapping_entry, expand_child_nodes):
                    index = result['end']
                else:
                    # If the child file doesn't exist, we'll need to write the child token as-is
                    index = result['start']

        # We've processed all the children, and we need to write the rest of the tree
        last_chunk = tree[index:]

        # Write the last chunk, but exclude the last name:edge_length, which needs special handling
        last_closed_bracket = last_chunk.rfind(')')
        output_stream.write(last_chunk[:last_closed_bracket+1])

        # Parse the last token into the node name and edge length
        last_token = last_chunk[last_closed_bracket+1:]
        last_token_segments = last_token.split(':')
        last_token_name = last_token_segments[0]
        last_token_edge_length = last_token_segments[1] if len(last_token_segments) > 1 else None

        # Always favor the length from our mapping, falling back to the last token in the file
        # Note that we never fall back to edge_length_in_parent here, following old code logic
        # DISCUSS: should we?
        edge_length = mapping_entry['edge_length'] if mapping_entry else None
        edge_length = edge_length or last_token_edge_length

        if mapping_entry:
            # Three levels of fallback for .PHY files: mapping, last token, parent
            node_name = mapping_entry['taxon'] or last_token_name or node_name_in_parent
        else:
            # Note that following old code logic, the parent vs last logic is reversed from above case
            # DISCUSS: is there a logical reason for this?
            node_name = node_name_in_parent or last_token_name

        output_stream.write(node_name)
        if edge_length:
            output_stream.write(f":{edge_length}")

        return True

    # Assume that the base file is in the same folder as the OneZoom parts
    oz_parts_folder = os.path.dirname(base_file)

    process_newick(base_file, expand_nodes=True)
    
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verbosity', '-v', action='count', default=0, help='verbosity level: output extra non-essential info')
    parser.add_argument('treefile', help='The base tree file in newick form')
    parser.add_argument('ot_parts_folder', help='The folder containing the Open Tree parts')
    parser.add_argument('outfile', type=argparse.FileType('w'), nargs='?', default=sys.stdout, help='The output tree file')
    args = parser.parse_args()

    if args.verbosity==0:
        logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    elif args.verbosity==1:
        logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    elif args.verbosity==2:
        logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

    build_oz_tree(args.treefile, args.ot_parts_folder, args.outfile)
    args.outfile.write(';')

if __name__ == '__main__':
    main()