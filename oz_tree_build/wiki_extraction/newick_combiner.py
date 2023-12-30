"""
Takes as input a .wikiclades file, which defines a list of trees to combine into a single tree.
Each tree comes from a wiki page, and is specified by the page name and the location of the tree within the page.
The output tree is in Newick format.
"""

import argparse
import logging
import dendropy
from oz_tree_build.utilities.debug_util import parse_args_and_add_logging_switch

from oz_tree_build.wiki_extraction.wiki_extractor import get_taxon_tree_from_wiki_page


def find_node_by_taxon(tree, taxon):
    # Replace underscores with spaces since Dendropy uses spaces
    taxon = taxon.replace("_", " ")
    node = tree.find_node_with_taxon_label(taxon)
    if not node:
        node = tree.find_node_with_label(taxon)
    if not node:
        raise Exception(f"Could not find node for taxon '{taxon}'")
    return node


def insert_child_tree(parent_tree, child_tree, taxon, child_taxon):
    node_in_parent_tree = find_node_by_taxon(parent_tree, taxon)

    # If the child taxon is "$ROOT", we use the root node of the child tree
    # This is useful when the root of the child tree is unnamed
    if child_taxon == "$ROOT":
        node_in_child_tree = child_tree.seed_node
    else:
        node_in_child_tree = find_node_by_taxon(child_tree, child_taxon)

    # We either replace the node, or add a child to it
    if child_taxon != taxon:
        node_in_parent_tree.add_child(node_in_child_tree)
    else:
        node_in_parent_tree.set_child_nodes(node_in_child_tree.child_nodes())


def process_file(filename, use_line_number_as_edge_length):
    main_tree = None
    for line_number, line in enumerate(open(filename)):
        # Ignore # comments
        if "#" in line:
            line = line[: line.index("#")]

        # Ignore blank lines
        line = line.strip()
        if line == "":
            continue

        tokens = line.split()

        # Lines look like:
        #   Dinosauria FROM Dinosaur@Taxonomy   # Taxomomy case
        #   Ornithischia FROM Ornithischia@1    # Cladogram case
        #   Ceratosauroidea->Ceratosauria FROM Ceratosauria@2   # Add a child instead of replacing the node
        if len(tokens) != 3:
            raise Exception(f"Invalid line: {line}")

        taxon = tokens[0]
        assert tokens[1] == "FROM"

        source = tokens[2]
        page_name, location = source.split("@")

        child_tree = get_taxon_tree_from_wiki_page(page_name, location)

        if use_line_number_as_edge_length:
            # Go through all the nodes and set the edge lengths to be the line number.
            # This is useful for debugging. Add 1 to it, since editors are 1 based
            for node in child_tree.nodes():
                if node.label or node.taxon:
                    node.edge_length = line_number + 1

        if "->" in taxon:
            # Here, the child taxon is different from the parent taxon, and will be *added* to it
            # e.g. "the_child->the_parent"
            child_taxon, taxon = taxon.split("->")
        else:
            child_taxon = taxon

        # Check for excluded taxa, e.g. "foo-bar-baz"
        parts = child_taxon.split("-")
        child_taxon = parts[0]
        excluded_taxa = parts[1:]

        # Remove all excluded taxa from the child tree
        for excluded_taxon in excluded_taxa:
            node = find_node_by_taxon(child_tree, excluded_taxon)
            parent = node.parent_node
            parent.remove_child(node)

        # For the parent taxon, we ignore all the exclusions. They're only there
        # since we use the same string for parent and child in the shorthand
        taxon = taxon.split("-")[0]

        if not main_tree:
            main_tree = dendropy.Tree()
            main_tree.seed_node = find_node_by_taxon(child_tree, taxon)
        else:
            insert_child_tree(main_tree, child_tree, taxon, child_taxon)

    return main_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "wikiclades_file",
        type=str,
        help="Path to the .wikiclades file",
    )
    parser.add_argument(
        "--use_line_number_as_edge_length",
        action="store_true",
        help="Use line number as edge length",
    )
    args = parse_args_and_add_logging_switch(parser)

    tree = process_file(args.wikiclades_file, args.use_line_number_as_edge_length)

    # Print the combined tree
    print(tree.as_string(schema="newick"))

    # Check for duplicate taxons in the tree
    taxons = set()
    for node in tree.nodes():
        taxon = node.label or node.taxon.label
        if not taxon:
            continue
        if taxon in taxons:
            logging.error(f"Duplicate taxon: {taxon}")
            continue
        taxons.add(taxon)

    # Log the number of nodes and leaves
    logging.info(
        f"Tree has {len(tree.nodes())} nodes and {len(tree.leaf_nodes())} leaves"
    )


if __name__ == "__main__":
    main()
