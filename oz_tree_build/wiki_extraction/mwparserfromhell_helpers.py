"""
Helper functions for extracting data from Wikipedia using mwparserfromhell
"""

import logging
import re
import mwparserfromhell
import requests_cache


session = requests_cache.CachedSession("http_cache")

API_URL = "https://en.wikipedia.org/w/api.php"


def get_text_from_wiki_page(page_title):
    # Doc: https://www.mediawiki.org/wiki/API:Revisions
    params = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "rvlimit": 1,
        "titles": page_title,
        "format": "json",
        "formatversion": "2",
        "redirects": "1",
    }
    headers = {"User-Agent": "My-Bot-Name/1.0"}
    req = session.get(API_URL, headers=headers, params=params, allow_redirects=True)
    res = req.json()
    try:
        revision = res["query"]["pages"][0]["revisions"][0]
        return revision["slots"]["main"]["content"]
    except KeyError:
        logging.warning(f"Could not find page '{page_title}'")
        return None


def get_wikicode_for_string(wiki_string) -> mwparserfromhell.wikicode.Wikicode:
    return mwparserfromhell.parse(wiki_string, skip_style_tags=True)


def get_wikicode_for_page(page_title) -> mwparserfromhell.wikicode.Wikicode:
    wiki_string = get_text_from_wiki_page(page_title)
    if not wiki_string:
        return None

    return get_wikicode_for_string(wiki_string)


def find_wikicode_node(wikicode, start_index, type, filter):
    for i, node in enumerate(wikicode.nodes[start_index:], start=start_index):
        assert wikicode.nodes[i] == node
        if isinstance(node, type) and filter(node):
            return i, node
    return None, None


# Helper to get a single-instance template, with flexible name matching
def get_wikicode_template(wikicode, possible_names) -> mwparserfromhell.nodes.Template:
    templates = wikicode.filter_templates(
        matches=lambda n: n.name.strip().casefold().replace(" ", "").replace("_", "")
        in possible_names
    )
    if len(templates) == 0:
        return None

    # It's expected to be a single instance template
    assert len(templates) == 1
    return templates[0]


def validate_clean_taxon(taxon, allow_shortened_binomial=False):
    # Remove any heading/trailing punctuation
    taxon = taxon.strip().strip("[]()'†?\"")

    # Deal with scenario where one word of the taxon is double-quoted
    # e.g. '"Nanshiungosaurus" bohlini'
    taxon = taxon.replace('"', "")

    if allow_shortened_binomial:
        # If we allow th shortened "P. Leo" form, allow periods and spaces
        if not re.match("^[a-zA-Z0-9. ]*$", taxon):
            return None
    elif not taxon.replace(" ", "").isalnum():
        # For the mainline case, don't allow periods
        return None

    # Some show up as e.g. "Unnamed species", which we ignore
    if taxon.startswith("Unnamed"):
        return None

    # If it has more than one space, it's probably not a valid taxon
    if taxon.count(" ") > 1:
        return None

    # If the second word has just 1 letter, it's probably not a valid taxon
    # e.g. Ornithurine A (from https://en.wikipedia.org/wiki/Ornithurae)
    if taxon.count(" ") == 1 and len(taxon.split(" ")[1]) == 1:
        return None

    return taxon


def get_taxon_name(
    wikicode,
    start_index=0,
    link_only=False,
    break_on_colon_or_star=False,  # Only true for taxonomy trees with bullet lists
    allow_shortened_binomial=False,  # True to allow shortened binomial names, e.g. "P. Leo"
    page_title=None,
    taxon_to_page_mapping=None,
):
    for node in wikicode.nodes[start_index:]:
        add_taxon_to_page_mapping = False
        using_text_node = False
        if isinstance(
            node, mwparserfromhell.nodes.Wikilink
        ) and not node.title.startswith("File:"):
            if node.text:
                # If the link has a display string, use that, but also save the page name
                # if it's different from the taxon name
                taxon = str(node.text)
                if node.text != node.title and taxon_to_page_mapping is not None:
                    add_taxon_to_page_mapping = True
            else:
                taxon = str(node.title)
        elif isinstance(node, mwparserfromhell.nodes.Text):
            using_text_node = True
            taxon = node.value
        elif isinstance(node, mwparserfromhell.nodes.tag.Tag):
            if break_on_colon_or_star and node.wiki_markup in [":", "*"]:
                break
            continue
        else:
            # Ignore all other types, e.g. HTMLEntity
            continue

        # This may return None if the taxon name is not usable
        taxon = validate_clean_taxon(taxon, allow_shortened_binomial)

        if taxon:
            # Ignore text nodes if we're only looking for links. However, if the text
            # is the same as the page title, we'll use it, since it's intrinsically a valid link
            if using_text_node and link_only and taxon != page_title:
                return None

            # Ignore it if it contains 2 uppercase letters in a row, e.g. "AZ"
            # This is a hack to skip non-species things like "SAM-PK-K8516 (from Cistecephalus AZ)"
            if re.search("[_A-Z]{2}", taxon):
                return None

            if add_taxon_to_page_mapping:
                taxon_to_page_mapping[taxon] = str(node.title)

            return taxon

    return None


# Look for a display string in a wikicode
def get_display_string_from_wikicode(wikicode, favor_link_title=False):
    for node in wikicode.nodes:
        if isinstance(
            node, mwparserfromhell.nodes.Wikilink
        ) and not node.title.startswith("File:"):
            if favor_link_title:
                display_string = str(node.title) if node.title else str(node.text)
            else:
                display_string = str(node.text) if node.text else str(node.title)
        elif isinstance(node, mwparserfromhell.nodes.Text):
            display_string = node.value
        else:
            # Ignore all other types, e.g. HTMLEntity
            continue

        # This may return None if the taxon name is not usable
        display_string = display_string.strip()

        if display_string:
            return display_string

    return None
