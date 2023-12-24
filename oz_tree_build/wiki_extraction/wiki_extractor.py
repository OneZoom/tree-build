# https://en.wikipedia.org/wiki/Template:Clade documents the clade template design

import argparse
import mwparserfromhell
import requests_cache
import dendropy
from oz_tree_build.wiki_extraction.mwparserfromhell_helpers import find_wikicode_node

from oz_tree_build.wiki_extraction.wiki_clade_node import WikiCladeNode
from oz_tree_build.wiki_extraction.wiki_taxonomy_node import WikiTaxonomyNode

session = requests_cache.CachedSession("http_cache")

API_URL = "https://en.wikipedia.org/w/api.php"


def get_text_from_wiki_page(title):
    params = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "rvlimit": 1,
        "titles": title,
        "format": "json",
        "formatversion": "2",
    }
    headers = {"User-Agent": "My-Bot-Name/1.0"}
    req = session.get(API_URL, headers=headers, params=params)
    res = req.json()
    revision = res["query"]["pages"][0]["revisions"][0]
    return revision["slots"]["main"]["content"]


def process_node(node):
    tree_node = dendropy.Node()
    tree_node.taxon = dendropy.Taxon(label=node.taxon)
    for child in node.enumerate_children():
        tree_node.add_child(process_node(child))
    return tree_node


def get_taxon_tree_from_wiki_page_string(wiki_page_string, location):
    wikicode = mwparserfromhell.parse(wiki_page_string, skip_style_tags=True)

    # If location string is a number, it's a cladogram index
    # If it's a string, it's a taxonomy header
    if location.isnumeric():
        node = WikiCladeNode.create_root_node(wikicode, int(location))
    else:
        node = WikiTaxonomyNode.create_root_node(wikicode, location)

    tree = dendropy.Tree()
    tree.seed_node = process_node(node)
    return tree.as_string(schema="newick")


def get_taxon_tree_from_wiki_page(wiki_title, location):
    wiki_string = get_text_from_wiki_page(wiki_title)

    return get_taxon_tree_from_wiki_page_string(wiki_string, location)


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
    args = parser.parse_args()

    args.location = args.location or 1

    if args.wiki_file:
        with open(args.wiki_file) as f:
            wiki_string = f.read()
        print(get_taxon_tree_from_wiki_page_string(wiki_string, args.location))
    else:
        print(get_taxon_tree_from_wiki_page(args.title, args.location))


if __name__ == "__main__":
    main()
