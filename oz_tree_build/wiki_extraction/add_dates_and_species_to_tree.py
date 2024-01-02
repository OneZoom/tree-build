"""
This script takes a tree in newick format and adds dates to the nodes based on
the Wikipedia fossil range data. It also adds a species name to each leaf node
based on the Wikipedia taxobox, if we don't already have a full species name.
"""

import argparse
import json
import logging
import sys
import dendropy
from oz_tree_build.utilities.debug_util import parse_args_and_add_logging_switch
from oz_tree_build.wiki_extraction.mwparserfromhell_helpers import (
    get_taxon_name,
    get_wikicode_for_page,
    get_display_string_from_wikicode,
    get_wikicode_template,
)


# Periods from https://en.wikipedia.org/wiki/Geologic_time_scale
PERIOD_LOOKUP = {
    "permian": [298.9, 251.9],  # Period
    "early permian": [298.9, 273.01],  # subperiod (Cisuralian)
    "asselian": [298.9, 293.52],
    "sakmarian": [293.52, 290.1],
    "artinskian": [290.1, 283.5],
    "kungurian": [283.5, 273.01],
    "middle permian": [273.01, 259.51],  # subperiod (Guadalupian)
    "roadian": [273.01, 266.9],
    "wordian": [266.9, 264.28],
    "capitanian": [264.28, 259.51],
    "late permian": [259.51, 251.9],  # subperiod (Lopingian)
    "wuchiapingian": [259.51, 254.14],
    "changhsingian": [254.14, 251.9],
    "triassic": [251.9, 201.4],  # Period
    "early triassic": [251.9, 247.2],  # subperiod
    "induan": [251.9, 251.2],
    "olenekian": [251.2, 247.2],
    "middle triassic": [247.2, 237],  # subperiod
    "anisian": [247.2, 242],
    "ladinian": [242, 237],
    "late triassic": [237, 201.4],  # subperiod
    "carnian": [237, 227],
    "norian": [227, 208.5],
    "rhaetian": [208.5, 201.4],
    "jurassic": [201.4, 145],  # Period
    "early jurassic": [201.4, 174.7],  # subperiod
    "hettangian": [201.4, 199.5],
    "sinemurian": [199.5, 192.9],
    "pliensbachian": [192.9, 184.2],
    "toarcian": [184.2, 174.7],
    "middle jurassic": [174.7, 161.5],  # subperiod
    "aalenian": [174.7, 170.9],
    "bajocian": [170.9, 168.2],
    "bathonian": [168.2, 165.3],
    "callovian": [165.3, 161.5],
    "late jurassic": [161.5, 145],  # subperiod
    "oxfordian": [161.5, 154.8],
    "kimmeridgian": [154.8, 149.2],
    "tithonian": [149.2, 145],
    "cretaceous": [145, 66],  # Period
    "early cretaceous": [145, 100.5],
    "lower cretaceous": [145, 100.5],
    "berriasian": [145, 139.8],
    "valanginian": [139.8, 132.6],
    "hauterivian": [132.6, 125.77],
    "barremian": [125.77, 121.4],
    "aptian": [121.4, 113],
    "albian": [113, 100.5],
    "late cretaceous": [100.5, 66],
    "upper cretaceous": [100.5, 66],
    "cenomanian": [100.5, 93.9],
    "turonian": [93.9, 89.8],
    "coniacian": [89.8, 86.3],
    "santonian": [86.3, 83.6],
    "campanian": [83.6, 72.1],
    "maastrichtian": [72.1, 66],
    "paleogene": [66, 23.03],
    "paleocene": [66, 56],
    "danian": [66, 61.6],
    "selandian": [61.6, 59.2],
    "thanetian": [59.2, 56],
    "eocene": [56, 33.9],
    "ypresian": [56, 47.8],
    "lutetian": [47.8, 41.2],
    "bartonian": [41.2, 37.71],
    "priabonian": [37.71, 33.9],
    "oligocene": [33.9, 23.03],
    "rupelian": [33.9, 27.82],
    "chattian": [27.82, 23.03],
    "neogene": [23.03, 2.588],
    "miocene": [23.03, 5.333],
    "aquitanian": [23.03, 20.44],
    "burdigalian": [20.44, 15.97],
    "langhian": [15.97, 13.82],
    "serravallian": [13.82, 11.63],
    "tortonian": [11.63, 7.246],
    "messinian": [7.246, 5.333],
    "pliocene": [5.333, 2.58],
    "zanclean": [5.333, 3.6],
    "piacenzian": [3.6, 2.58],
    "quaternary": [2.58, 0],
    "pleistocene": [2.58, 0.0117],
    "gelasian": [2.58, 1.8],
    "calabrian": [1.8, 0.774],
    "chibanian": [0.774, 0.129],
    "late pleistocene": [0.129, 0.0117],
    "holocene": [0.0117, 0],
    "recent": [0, 0],
}


def map_period_name_to_range(period_name):
    period_name = period_name.lower()
    if period_name in PERIOD_LOOKUP:
        return PERIOD_LOOKUP[period_name]

    logging.warning(f"Unknown period name: {period_name}")
    return None


def get_range_date(fossilrange_value, use_start):
    if isinstance(fossilrange_value, str):
        # If it's already a string, use it as is
        date = fossilrange_value
    else:
        periodstart_template = get_wikicode_template(fossilrange_value, ("periodstart"))
        if not periodstart_template:
            date = str(fossilrange_value)
        else:
            date = str(periodstart_template.params[0].value)

    # Convert it to a float if it looks like a number
    try:
        date = float(date)
    except ValueError:
        # If it's not a number, it could be a period name. If so, we grab
        # either the start or end date
        date_range = map_period_name_to_range(date)
        if not date_range:
            return None

        date = date_range[0] if use_start else date_range[1]

    return date


def get_date_range_from_taxobox(taxobox):
    if not taxobox.has_param("fossil_range"):
        return None, None

    range = taxobox.get("fossil_range").value
    # Template name can randomly be be "fossil range" or "geological range", with or without space/underscores
    fossil_range_template = get_wikicode_template(
        range, ("fossilrange", "geologicalrange")
    )

    if not fossil_range_template:
        # If there is no template, just try to treat it as a string to get a range
        # We favor the link title, as in "Middle Permian" in [[Middle Permian|Middle]]
        range_string = get_display_string_from_wikicode(range, favor_link_title=True)
        if not range_string:
            return None, None
        from_date = to_date = get_range_date(range_string, use_start=True)
    else:
        from_date = get_range_date(
            fossil_range_template.params[0].value, use_start=True
        )
        # If there is no end date, we fall back to the start date
        to_date = (
            get_range_date(fossil_range_template.params[1].value, use_start=False)
            if len(fossil_range_template.params) >= 2
            else from_date
        )

    return from_date, to_date


def get_species_from_taxobox(taxon, taxobox):
    species_name = None
    if taxobox.has_param("type_species"):
        type_species = taxobox.get("type_species").value
        species_name = get_taxon_name(type_species)
    elif taxobox.has_param("genus") and taxobox.has_param("species"):
        genus = taxobox.get("genus").value
        species = taxobox.get("species").value
        species_name = get_taxon_name(genus) + " " + get_taxon_name(species)
    elif taxobox.has_param("subdivision"):
        subdivision = taxobox.get("subdivision").value
        species_name = get_taxon_name(subdivision, allow_shortened_binomial=True)
    elif taxobox.has_param("taxon"):
        taxon_prop_value = taxobox.get("taxon").value
        species_name = get_taxon_name(taxon_prop_value)

    if not species_name:
        logging.warning(f"Could not find species name for {taxon}")
        return None

    # Make sure it's a binomial species name
    if not " " in species_name:
        logging.warning(
            f"For {taxon}, found '{species_name}' in taxobox, but it's not binomial"
        )
        return None

    return species_name


nodes_data = {}
taxon_to_page_mapping = {}


def get_taxon_data_from_wikipedia(taxon, is_leaf):
    logging.info(f"Processing taxon '{taxon}'")

    # If we have a mapping from taxon to page title, use that. This is
    # the case where the link display didn't match the link target
    if taxon in taxon_to_page_mapping:
        page_title = taxon_to_page_mapping[taxon]
    else:
        page_title = taxon

    # Get the Wikipedia page for the taxon
    wikicode = get_wikicode_for_page(page_title)
    if not wikicode:
        return None

    taxobox = get_wikicode_template(wikicode, ("automatictaxobox", "speciesbox"))
    if not taxobox:
        logging.warning(f"Could not find taxobox for {taxon}")
        return None

    node_data = {}
    from_date, to_date = get_date_range_from_taxobox(taxobox)
    if not from_date:
        logging.warning(f"Could not find fossil range for {taxon}")

    # Note that for species, the end date is the extinction date
    node_data["from_date"] = from_date
    node_data["to_date"] = to_date

    if is_leaf:
        # If the taxon in the newick is not a binomial species name
        if " " not in taxon:
            # Try to get the species name from the taxobox
            species_name = get_species_from_taxobox(taxon, taxobox)
            if species_name:
                # If it starts with an uppercase letter followed by a period, replace
                # that with the taxon (which is the genus name). e.g. "P. Leo" -> "Panthera leo"
                if species_name[0].isupper() and species_name[1] == ".":
                    species_name = taxon + species_name[2:]
                node_data["species_name"] = species_name
            else:
                logging.warning(f"Could not find binomial species name for {taxon}")

    return node_data


def get_taxon_data_from_wikipedia_with_caching(taxon, is_leaf):
    if taxon in nodes_data:
        logging.info(f"Found cached data for {taxon}: '{nodes_data[taxon]}'")
        return nodes_data[taxon]

    nodes_data[taxon] = get_taxon_data_from_wikipedia(taxon, is_leaf)

    logging.info(f"{taxon}: '{nodes_data[taxon]}'")

    return nodes_data[taxon]


def process_leaf_node_and_get_extinction_date(node):
    # Find the node's taxon name
    if not node.taxon or not node.taxon.label:
        taxon = None
        logging.warning(f"Leaf node has no taxon: {node}")
        return 0

    taxon = node.taxon.label
    node_data = get_taxon_data_from_wikipedia_with_caching(taxon, is_leaf=True)

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
        node_data = get_taxon_data_from_wikipedia_with_caching(taxon, node.is_leaf())

    if not node_data:
        node_data = {}

    if node_data and "from_date" in node_data and node_data["from_date"]:
        date_range = [node_data["from_date"], node_data["to_date"]]
        if oldest_child_from_date > date_range[0]:
            logging.warning(
                f"Node '{taxon}' has from_date {node_data['from_date']}, but its child {child_with_oldest_from_date.taxon} has from_date {oldest_child_from_date}"
            )
            date_range[0] = oldest_child_from_date
    else:
        date_range = [oldest_child_from_date, 0]

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

    # Read the mapping from taxon to page title from the tree comments
    if tree.comments:
        taxon_to_page_mapping.update(json.loads(tree.comments[0]))

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
        json.dump(nodes_data, f)


if __name__ == "__main__":
    main()
