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


def get_clade_tree_from_wiki_page_string(
    wiki_page_string, index=None, taxonomy_header=None
):
    wikicode = mwparserfromhell.parse(wiki_page_string, skip_style_tags=True)

    if taxonomy_header:
        node = WikiTaxonomyNode.create_root_node(wikicode, taxonomy_header)
    else:
        node = WikiCladeNode.create_root_node(wikicode, index)

    tree = dendropy.Tree()
    tree.seed_node = process_node(node)
    return tree.as_string(schema="newick")


def get_clade_tree_from_wiki_page(wiki_title, index=None, taxonomy_header=None):
    wiki_string = get_text_from_wiki_page(wiki_title)

    return get_clade_tree_from_wiki_page_string(wiki_string, index, taxonomy_header)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", type=str, help="Wikipedia page title")
    parser.add_argument(
        "--wiki_file",
        type=str,
        help="Path to the pre-downloaded wiki file",
    )
    parser.add_argument(
        "--cladogram_index",
        type=int,
        nargs="?",
        help="Index of the cladogram within the page",
    )
    parser.add_argument(
        "--taxonomy_header",
        type=str,
        nargs="?",
        help="Header of the taxonomy section",
    )

    args = parser.parse_args()

    if args.wiki_file:
        with open(args.wiki_file) as f:
            wiki_string = f.read()
        print(
            get_clade_tree_from_wiki_page_string(
                wiki_string, args.cladogram_index, args.taxonomy_header
            )
        )
    else:
        print(
            get_clade_tree_from_wiki_page(
                args.title, args.cladogram_index, args.taxonomy_header
            )
        )


if __name__ == "__main__":
    main()
