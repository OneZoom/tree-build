'''
Lightweight Newick parser that takes a string and enumerate all the nodes in the tree.

It's a very simple one-pass parser that doesn't build any parse tree, and instead processes
the nodes as they're read. It's designed to be fast.

The nodes are returned in post-order (children before parent), which is the Newick order.

For simplicity, it assumes that the tree string has no spaces.

Here is a trivial example of how to use it:

    for node in parse_tree("(A_ott123,B:1.2)C_ott789:5.5;"):
        print(f"Node: {node['taxon']}, OTT: {node['ott']}, Edge length: {node['edge_length']}")

It produces the following output:
    Node: A, OTT: 123, Edge length: 0.0
    Node: B, OTT: None, Edge length: 1.2
    Node: C, OTT: 789, Edge length: 5.5
'''

import re
from typing import Set

__author__ = "David Ebbo"

non_name_regex = re.compile(r'[,;:\(\)]')

def parse_tree(newick_tree):
    index = 0
    index_stack = []
    closed_brace = False

    # Helper function to raise a syntax error with extra context
    def raise_syntax_error(message):
        raise SyntaxError(message, (None, 0, min(index, 20), newick_tree[max(index-20,0):index+20]))

    while True:
        if newick_tree[index] == '(':
            index_stack.append(index)
            index += 1
            continue

        if closed_brace:
            index += 1

            # Set the start index to the beginning of the node (where the open parenthesis is)
            node_start_index = index_stack.pop()
        else:
            node_start_index = index

        taxon = ott = None

        # Parse the taxon name, either quoted or unquoted
        full_name_start_index = index
        if newick_tree[index] == "'":
            # This is a quoted name, so we need to find the matching end quote
            end_quote_index = newick_tree.index("'", index+1)

            taxon = newick_tree[index+1:end_quote_index]
            index = end_quote_index + 1
        else:
            # This may be an unquoted name, so we need to find the end
            match = non_name_regex.search(newick_tree, index)
            if match:
                index = match.start()
                taxon = newick_tree[full_name_start_index:index]

        # After the taxon, there may be an edge length
        edge_length = 0.0
        if newick_tree[index] == ':':
            index += 1
            match = non_name_regex.search(newick_tree, index)
            if match:
                # Convert to a float
                try:
                    edge_length_str = newick_tree[index:match.start()]
                    edge_length = float(edge_length_str)
                except ValueError:
                    raise_syntax_error(f"'{edge_length_str}' is not a valid edge length")
                index = match.start()

        if taxon:
            # Check if the taxon has an ott id, and if so, parse it out
            if '_ott' in taxon:
                ott_index = taxon.index('_ott')
                ott = taxon[ott_index+4:]
                taxon = taxon[:ott_index]

        yield {'taxon': taxon, 'ott': ott, 'edge_length': edge_length,
                'start': node_start_index, 'end': index, 'full_name_start_index': full_name_start_index,
                'depth': len(index_stack), 'is_leaf': not closed_brace}

        # If the stack is empty, we've balanced all the braces and we're done
        if len(index_stack) == 0:
            break

        # After a taxon, we expect a comma or a closed brace
        closed_brace = newick_tree[index] == ')'
        if newick_tree[index] == ',':
            index += 1
        elif not closed_brace:
            raise_syntax_error(f"expected ',' or ')'")

    if index == len(newick_tree) or newick_tree[index] != ';':
        raise_syntax_error(f"expected a semicolon at the end of the tree")
