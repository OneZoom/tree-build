"""
Extracts a taxon tree from a Wikipedia page.

It supports two types of wikipedia trees.

The first is a taxonomy tree, which is a bullet list of taxa. Here, the location is the name of the header
that precedes the bullet list. Example command:
    python3 wiki_extractor.py --title Dinosaur --location 1 Taxonomy

The second is a wikipedia cladogram template. Here, the location is the index of the cladogram within the page.
Example command:
    python3 wiki_extractor.py --title Ornithischia --location 1

The output is a Newick tree, which is printed to stdout.
"""

import argparse
import logging

import dendropy

from oz_tree_build.utilities.debug_util import parse_args_and_add_logging_switch
from oz_tree_build.wiki_extraction.mwparserfromhell_helpers import (
    get_wikicode_for_page,
    get_wikicode_for_string,
)
from oz_tree_build.wiki_extraction.wiki_clade_node import WikiCladeNode
from oz_tree_build.wiki_extraction.wiki_taxonomy_node import WikiTaxonomyNode


def process_node(node, taxon_set) -> dendropy.Node:
    tree_node = dendropy.Node()
    if node.taxon:
        if node.taxon not in taxon_set:
            tree_node.taxon = dendropy.Taxon(label=node.taxon)
            taxon_set.add(node.taxon)
        else:
            # In rare cases, the same taxon appears twice in the same tree.
            # e.g. this occurs in the Amniota tree, which has both 'Amniota (total group)'
            # and 'Amniota (crown group)'. To avoid issues, we just ignore the second instance.
            logging.warning(f"Ignoring taxon {node.taxon}, as it already exists in the same tree")
    for child in node.enumerate_children():
        tree_node.add_child(process_node(child, taxon_set))

    # Add the page title as a comment if it's different from the taxon
    if node.taxon_page_title and node.taxon_page_title != node.taxon:
        tree_node.comments.append(node.taxon_page_title)
    return tree_node


def get_taxon_tree_from_wikicode(page_title, wikicode, taxon_tree_location) -> dendropy.Tree:
    # If location string is a number, it's a cladogram index
    # If it's a string, it's the wiki header that precedes a taxonomy tree (bullet list)
    if taxon_tree_location.isnumeric():
        node = WikiCladeNode.create_root_node(page_title, wikicode, int(taxon_tree_location))
    else:
        node = WikiTaxonomyNode.create_root_node(page_title, wikicode, taxon_tree_location)

    tree = dendropy.Tree()
    taxon_set = set()
    tree.seed_node = process_node(node, taxon_set)
    return tree


def get_taxon_tree_from_wiki_page(wiki_title, taxon_tree_location) -> dendropy.Tree:
    wikicode = get_wikicode_for_page(wiki_title)
    return get_taxon_tree_from_wikicode(wiki_title, wikicode, taxon_tree_location)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", type=str, help="Wikipedia page title")
    parser.add_argument(
        "--wiki_file",
        type=str,
        help="Path to the pre-downloaded wiki file",
    )
    parser.add_argument(
        "--location",
        type=str,
        nargs="?",
        help="Index of the cladogram within the page, or name of the taxonomy header",
    )
    args = parse_args_and_add_logging_switch(parser)

    args.location = args.location or 1

    if args.wiki_file:
        with open(args.wiki_file) as f:
            wiki_string = f.read()
        wikicode = get_wikicode_for_string(wiki_string)
    else:
        wikicode = get_wikicode_for_page(args.title)

    tree = get_taxon_tree_from_wikicode(args.title, wikicode, args.location)
    print(tree.as_string(schema="newick"))


if __name__ == "__main__":
    main()
