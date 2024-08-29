"""
Helper functions for extracting data from Wikipedia using mwparserfromhell
"""

import logging
import re

import mwparserfromhell
import requests_cache

session = requests_cache.CachedSession("http_cache")

API_URL = "https://en.wikipedia.org/w/api.php"


def get_id_and_text_from_wiki_page(page_title):
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
        page = res["query"]["pages"][0]
        revision = page["revisions"][0]
        page_id = page["pageid"]
        return page_id, revision["slots"]["main"]["content"]
    except KeyError:
        logging.warning(f"Could not find page '{page_title}'")
        return None, None


def get_wikicode_for_string(wiki_string) -> mwparserfromhell.wikicode.Wikicode:
    return mwparserfromhell.parse(wiki_string, skip_style_tags=True)


def get_wikicode_for_page(page_title) -> mwparserfromhell.wikicode.Wikicode:
    page_id, wiki_string = get_id_and_text_from_wiki_page(page_title)
    if not wiki_string:
        return None

    wikicode = get_wikicode_for_string(wiki_string)
    # Add the pageid as a wikicode property for convenience
    wikicode.page_id = page_id
    return wikicode


def find_wikicode_node(wikicode, start_index, node_type, node_filter):
    for i, node in enumerate(wikicode.nodes[start_index:], start=start_index):
        assert wikicode.nodes[i] == node
        if isinstance(node, node_type) and node_filter(node):
            return i, node
    return None, None


# Helper to get a single-instance template, with flexible name matching
def get_wikicode_template(wikicode, possible_names) -> mwparserfromhell.nodes.Template:
    templates = wikicode.filter_templates(
        matches=lambda n: n.name.strip().casefold().replace(" ", "").replace("_", "") in possible_names
    )
    if len(templates) == 0:
        return None

    # It's expected to be a single instance template
    assert len(templates) == 1
    return templates[0]


rank_names = [
    "Total-group",  # Used in https://en.wikipedia.org/wiki/Artiodactyl for Ruminantia
    "Clade",
    "Class",
    "Superfamily",
    "Family",
    "Subfamily",
    "Tribe",
    "Superorder",
    "Order",
    "Suborder",
    "Infraorder",
    "Parvorder",
    "Genus",
    "Species",
]


def validate_clean_taxon(taxon, allow_shortened_binomial=False):
    # In some cases, the taxon is a combination of two taxa, and we just pick the first one
    # e.g. "Order Artiodactyla/Clade Cetartiodactyla" from https://en.wikipedia.org/wiki/Artiodactyl
    if "/" in taxon:
        taxon = taxon.split("/")[0]

    # Remove any heading/trailing punctuation/markup
    taxon = taxon.strip().strip("[]()'†?\"")

    # Check if taxon starts with a rank_names, ignore the rank name (e.g. Family [[Cyamodontidae]])
    for rank_name in rank_names:
        if taxon.startswith(rank_name):
            taxon = taxon[len(rank_name) :]
            taxon = taxon.strip().strip("[]()'†?\"")
            if not taxon:
                return None
            break

    # Deal with scenario where one word of the taxon is double-quoted
    # e.g. '"Nanshiungosaurus" bohlini'
    taxon = taxon.replace('"', "")

    taxon_for_alphanum_check = taxon.replace(" ", "").replace("-", "")
    if allow_shortened_binomial and len(taxon_for_alphanum_check) > 1 and taxon_for_alphanum_check[1] == ".":
        # If we allow shortened binomial names (e.g. "P. Leo"), remove the period if any
        taxon_for_alphanum_check = taxon_for_alphanum_check[0] + taxon_for_alphanum_check[2:]
    if not taxon_for_alphanum_check.replace(" ", "").isalnum():
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


def get_taxon_and_page_title(
    wikicode,
    start_index=0,
    link_only=False,
    break_on_colon_or_star=False,  # Only true for taxonomy trees with bullet lists
    allow_shortened_binomial=False,  # True to allow shortened binomial names, e.g. "P. Leo"
    containing_page_title=None,  # Title of the page containing the wikicode
):
    for index, node in enumerate(wikicode.nodes[start_index:]):
        # Use the index variable here
        taxon_page_title = None
        using_text_node = False
        if isinstance(node, mwparserfromhell.nodes.Wikilink) and not node.title.startswith("File:"):
            if node.text:
                # If the link has a display string, use that
                taxon = str(node.text)
            else:
                taxon = str(node.title)
            taxon_page_title = str(node.title)

            # If it's not already binomial, and the next node is text,
            # try to include that in the taxon name. This covers cases like
            # ''[[Mosasaurus]] hoffmannii'' (from https://en.wikipedia.org/wiki/Mosasaurinae)
            if " " not in taxon and index + 1 < len(wikicode.nodes):
                node = wikicode.nodes[index + 1]
                if isinstance(node, mwparserfromhell.nodes.Text):
                    taxon2 = validate_clean_taxon(node.value)
                    # Ignore the extra part of it contains a '(', as in |2=[[Serpentes]] (modern snakes)
                    if taxon2 and "(" not in node.value:
                        taxon = taxon + " " + taxon2
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
            # is the same as the page title (or at least starts with it),
            # we'll use it, since it's intrinsically a valid link
            if (
                using_text_node
                and link_only
                and (not containing_page_title or not taxon.startswith(containing_page_title))
            ):
                return None, None

            # Ignore it if it contains 2 uppercase letters in a row, e.g. "AZ"
            # This is a hack to skip non-species things like "SAM-PK-K8516 (from Cistecephalus AZ)"
            if re.search("[_A-Z]{2}", taxon):
                return None, None

            return taxon, taxon_page_title

    return None, None


def get_taxon_name(
    wikicode,
    allow_shortened_binomial=False,  # True to allow shortened binomial names, e.g. "P. Leo"
):
    taxon, _ = get_taxon_and_page_title(
        wikicode,
        allow_shortened_binomial=allow_shortened_binomial,
    )
    return taxon


# Look for a display string in a wikicode
def get_display_string_from_wikicode(wikicode, favor_link_title=False):
    for node in wikicode.nodes:
        if isinstance(node, mwparserfromhell.nodes.Wikilink) and not node.title.startswith("File:"):
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
