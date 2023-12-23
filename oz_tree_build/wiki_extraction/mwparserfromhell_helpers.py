import re
import mwparserfromhell


def find_wikicode_node(wikicode, start_index, type, func):
    for i, node in enumerate(wikicode.nodes[start_index:], start=start_index):
        assert wikicode.nodes[i] == node
        if isinstance(node, type) and func(node):
            return i, node
    return None, None


def validate_clean_taxon(taxon):
    # Remove any heading/trailing punctuation
    taxon = taxon.strip().strip("[]()'" "†? ")

    # If the string contains anything other than letters, we can't use it
    if not taxon.replace(" ", "").isalnum():
        return None

    # Ignore it if it contains 2 uppercase letters in a row, e.g. "AZ"
    # This is a hack to skip non-species things like "SAM-PK-K8516 (from Cistecephalus AZ)"
    if re.search("[A-Z]{2}", taxon):
        return None

    # Some show up as e.g. "Unnamed species", which we ignore
    if taxon.startswith("Unnamed"):
        return None

    return taxon


def get_taxon_name(wikicode, index=0):
    for node in wikicode.nodes[index:]:
        if isinstance(node, mwparserfromhell.nodes.Wikilink):
            taxon = str(node.text) if node.text else str(node.title)
        elif isinstance(node, mwparserfromhell.nodes.Text):
            taxon = node.value
        elif isinstance(node, mwparserfromhell.nodes.tag.Tag):
            # Never go past a colon or asterisk, which start a new taxonomy item
            # (not relevant for clade diagrams, but harmless)
            if node.wiki_markup in [":", "*"]:
                break
            continue
        else:
            # Ignore all other types, e.g. HTMLEntity
            continue

        # This may return None if the taxon name is not usable
        taxon = validate_clean_taxon(taxon)
        if taxon:
            return taxon

    return None
