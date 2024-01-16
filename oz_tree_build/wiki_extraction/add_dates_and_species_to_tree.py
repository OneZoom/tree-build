"""
This script takes a tree in newick format and adds dates to the nodes based on
the Wikipedia fossil range data. It also adds a species name to each leaf node
based on the Wikipedia taxobox, if we don't already have a full species name.
"""

import argparse
import json
import logging
import dendropy
from oz_tree_build.utilities.debug_util import parse_args_and_add_logging_switch
from oz_tree_build.wiki_extraction.wiki_taxon_page_data import (
    get_taxon_data_from_wikipedia_page,
)


nodes_data = {}


def get_taxon_data_from_wikipedia_with_caching(taxon, page_title, is_leaf):
    if taxon in nodes_data:
        logging.info(f"Found cached data for {taxon}: '{nodes_data[taxon]}'")
        return nodes_data[taxon]

    nodes_data[taxon] = get_taxon_data_from_wikipedia_page(taxon, page_title, is_leaf)

    logging.info(f"{taxon}: '{nodes_data[taxon]}'")

    return nodes_data[taxon]


# If the node has a comment, use that as the page title instead of the taxon
# This is the case where the link display didn't match the link target
def get_wiki_page_title(taxon, node):
    if len(node.comments) > 0:
        return node.comments[0]

    return taxon


def process_leaf_node_and_get_extinction_date(node):
    # Find the node's taxon name
    if not node.taxon or not node.taxon.label:
        taxon = None
        logging.warning(f"Leaf node has no taxon: {node}")
        return 0

    taxon = node.taxon.label

    node_data = get_taxon_data_from_wikipedia_with_caching(
        taxon, get_wiki_page_title(taxon, node), is_leaf=True
    )

    # If we couldn't get any data (missing page or no taxobox), delete the node,
    # since we won't be able to show anything interesting for it
    if node_data is None:
        logging.warning(f"Ignoring leaf node with no data: {taxon}")
        node.parent_node.remove_child(node)
        return None

    extinction_date = 0
    if node_data:
        if "to_date" in node_data:
            extinction_date = node_data["to_date"] or 0

        if "species_name" in node_data:
            node.taxon.label = node_data["species_name"]

    # If it's an extinct leaf, add a nameless prop-up node with the date
    if extinction_date:
        extinction_propup_node = dendropy.Node()
        extinction_propup_node.edge_length = extinction_date
        node.add_child(extinction_propup_node)

    return extinction_date


def process_interior_node_recursive_and_get_range(node):
    # Find the oldest 'from' date of all the children ranges
    oldest_child_from_date = 0
    child_with_oldest_from_date = None
    children_date_ranges = {}
    for child in node.child_nodes():
        child_date_range = process_node_recursive_and_get_range(child)
        if not child_date_range:
            continue
        if child_date_range[0]:
            if child_date_range[0] > oldest_child_from_date:
                oldest_child_from_date = child_date_range[0]
                child_with_oldest_from_date = child
        children_date_ranges[child] = child_date_range

    # Find the node's taxon name (interior nodes may not have a taxon)
    taxon = node.taxon and node.taxon.label

    # If we have a taxon name, get data from Wikipedia
    node_data = None
    if taxon:
        node_data = get_taxon_data_from_wikipedia_with_caching(
            taxon, get_wiki_page_title(taxon, node), node.is_leaf()
        )

    if not node_data:
        node_data = {}

    if "from_date" in node_data and node_data["from_date"]:
        date_range = [node_data["from_date"], node_data["to_date"]]
        if oldest_child_from_date > date_range[0]:
            logging.warning(
                f"Node '{taxon}' has from_date {node_data['from_date']}, but its child {child_with_oldest_from_date.taxon} has from_date {oldest_child_from_date}"
            )
            date_range[0] = round(oldest_child_from_date + 0.001, 10)
    else:
        # If we don't have a range for this node, use the oldest child's date,
        # plus a small amount (1000y) to avoid making it look like a polytomy
        date_range = [round(oldest_child_from_date + 0.001, 10), 0]

    # Set the edge length for all the children
    for child in node.child_nodes():
        if child in children_date_ranges:
            child_date_range = children_date_ranges[child]
            child.edge_length = round(date_range[0] - child_date_range[0], 10)
            assert child.edge_length >= 0

    return date_range


def process_node_recursive_and_get_range(node):
    if node.is_leaf():
        extinction_date = process_leaf_node_and_get_extinction_date(node)
        if extinction_date is None:
            return None

        # For a leaf, set the end date to the start date, since that's what we'll
        # want to use for the calculation of the edge length to its parent
        return [extinction_date, extinction_date]
    else:
        return process_interior_node_recursive_and_get_range(node)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "treefile",
        type=argparse.FileType("r"),
        help="The tree file in newick form",
    )
    args = parse_args_and_add_logging_switch(parser)

    # Parse the input tree
    tree = dendropy.Tree.get(
        file=args.treefile, schema="newick", suppress_internal_node_taxa=False
    )

    # The taxon data cache file has the same name with a .json extension
    cache_filename = args.treefile.name + ".taxondatacache.json"
    try:
        with open(cache_filename) as f:
            nodes_data.update(json.load(f))
    except FileNotFoundError:
        pass

    process_node_recursive_and_get_range(tree.seed_node)

    # Print the updated tree
    print(tree.as_string(schema="newick"))

    # Save the taxon data cache file
    with open(cache_filename, "w") as f:
        json.dump(nodes_data, f, sort_keys=True, indent=2)


if __name__ == "__main__":
    main()
