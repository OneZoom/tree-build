"""
For a given taxon Wikipedia page, extract various bits of information: the
species name and the date range of its existence. This is done by parsing the
page's wikicode and looking for specific templates and patterns. The
information is returned as a dictionary.
"""


import logging

from oz_tree_build.wiki_extraction.mwparserfromhell_helpers import (
    get_display_string_from_wikicode,
    get_taxon_name,
    get_wikicode_for_page,
    get_wikicode_template,
)
from oz_tree_build.wiki_extraction.period_date_ranges import map_period_name_to_range


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
        from_date = get_range_date(range_string, use_start=True)
        to_date = get_range_date(range_string, use_start=False)
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
        # Species can be either the full binomial name, or just the specific name
        species = taxobox.get("species").value
        species_name = get_taxon_name(species, allow_shortened_binomial=True)

        # If it's already binomial, we're done
        if species_name and not " " in species_name:
            species_name = get_taxon_name(genus) + " " + species_name
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


def get_taxon_data_from_wikipedia_page(taxon, page_title, is_leaf):
    logging.info(f"Processing taxon '{taxon}'")

    # Get the Wikipedia page for the taxon
    wikicode = get_wikicode_for_page(page_title)
    if not wikicode:
        return None

    taxobox = get_wikicode_template(
        wikicode, ("automatictaxobox", "speciesbox", "taxobox")
    )
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
