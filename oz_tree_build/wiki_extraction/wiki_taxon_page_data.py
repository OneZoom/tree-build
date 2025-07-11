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
        periodstart_template = get_wikicode_template(fossilrange_value, ("periodstart",))
        if not periodstart_template:
            date = str(fossilrange_value).strip()
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

    fossil_range = taxobox.get("fossil_range").value
    # Template name can randomly be be "fossil range" or "geological range", with or without space/underscores
    fossil_range_template = get_wikicode_template(
        fossil_range,
        ("fossilrange", "geologicalrange", "geologicalrange/linked", "geologicalage"),
    )

    if not fossil_range_template:
        # If there is no template, just try to treat it as a string to get a range
        # We favor the link title, as in "Middle Permian" in [[Middle Permian|Middle]]
        range_string = get_display_string_from_wikicode(fossil_range, favor_link_title=True)
        if not range_string:
            return None, None
        from_date = get_range_date(range_string, use_start=True)
        to_date = get_range_date(range_string, use_start=False)
    else:
        # If the first param is "earliest", we skip it.
        # e.g. Stegosauria has {{fossilrange|earliest=174|169|100|latest=66}}
        param_index = 0
        if fossil_range_template.params[0].name == "earliest":
            param_index = 1
        from_date = get_range_date(fossil_range_template.params[param_index].value, use_start=True)
        # If there is no end date, we fall back to the start date
        to_date = (
            get_range_date(fossil_range_template.params[param_index + 1].value, use_start=False)
            if len(fossil_range_template.params) >= param_index + 2
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
        if species_name and " " not in species_name:
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
    if " " not in species_name:
        logging.warning(f"For {taxon}, found '{species_name}' in taxobox, but it's not binomial")
        return None

    # Ignore some bogus values that can appear (e.g. see https://en.wikipedia.org/wiki/Protosuchia)
    if species_name == "See text":
        logging.warning(f"Ignoring bogus species name '{species_name}' for {taxon}")
        return None

    return species_name


def get_qid_from_wikicode(wikicode):
    taxonbar = get_wikicode_template(wikicode, ("taxonbar",))
    if not taxonbar:
        return None

    # Normally, the QID is in the "from" param. But in cases like https://en.wikipedia.org/wiki/Miopanthera,
    # there are multiple QIDs, and the params are named "from1", "from2", etc.
    if taxonbar.has_param("from"):
        qid_string = taxonbar.get("from")
    elif taxonbar.has_param("from1"):
        qid_string = taxonbar.get("from1")
    return int(qid_string.value.strip()[1:])


def get_image_from_page(wikicode, taxobox):
    image_name = None

    # First, check if we can find a paleoart image anywhere in the page
    # "Restoration", "Reconstruction", "Life restoration" or "Life reconstruction" are common titles for those
    paleoart_links = wikicode.filter_wikilinks(
        matches=lambda l: "restoration" in str(l.text).lower() or "reconstruction" in str(l.text).lower()
    )
    # Sort them so that those that contain "restoration" come first, since we prefer those
    paleoart_links = sorted(paleoart_links, key=lambda l: "restoration" in str(l.text).lower(), reverse=True)
    if len(paleoart_links) > 0:
        image_name = str(paleoart_links[0].title)

        # In some cases, the link is not directly to the image, but is contained
        # in a parent template with image properties multiple image
        # e.g. this happens for https://en.wikipedia.org/wiki/Tyrannosaurus
        if image_name and "." not in image_name:
            link_parent = wikicode.get_parent(paleoart_links[0])
            if link_parent:
                # Find the first param that starts with "image". Could be "image1" or just "image"
                image_name = None
                for param in link_parent.params:
                    if param.name.strip().startswith("image"):
                        image_name = str(param.value).strip()
                        break
            else:
                image_name = None

    # Otherwise, just use the taxobox image, if any
    if not image_name and taxobox.has_param("image"):
        image = taxobox.get("image")

        # If it's a multiple image template, we use the first image
        multiple_image = get_wikicode_template(image.value, ("multipleimage",))
        if multiple_image:
            image = multiple_image.get("image1")

        image_name = str(image.value).strip()

    # The '<' part is to ignore an odd case of HTML for Aves
    if not image_name or "<" in image_name:
        return None

    # Remove any leading "File:" or "Image:"
    if ":" in image_name:
        image_name = image_name.split(":")[1]

    return image_name


def get_taxon_data_from_wikipedia_page(taxon, page_title, is_leaf):
    logging.info(f"Processing taxon '{taxon}'")

    # Get the Wikipedia page for the taxon
    wikicode = get_wikicode_for_page(page_title)
    if not wikicode:
        return None

    taxobox = get_wikicode_template(wikicode, ("automatictaxobox", "speciesbox", "taxobox"))
    if not taxobox:
        logging.warning(f"Could not find taxobox for {taxon}")
        return None

    # Persist the wikipedia page id
    node_data = {"page_id": wikicode.page_id}
    from_date, to_date = get_date_range_from_taxobox(taxobox)
    if not from_date:
        logging.warning(f"Could not find fossil range for {taxon}")

    # Get the Wikidata QID, if any
    qid = get_qid_from_wikicode(wikicode)
    if qid:
        node_data["qid"] = qid

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

        image = get_image_from_page(wikicode, taxobox)
        if image:
            node_data["image"] = image

    return node_data
