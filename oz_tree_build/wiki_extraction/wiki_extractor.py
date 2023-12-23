# https://en.wikipedia.org/wiki/Template:Clade documents the clade template design

import argparse
import mwparserfromhell
import requests_cache
import dendropy

from oz_tree_build.wiki_extraction.wiki_clade_node import WikiCladeNode

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
    tree_node.taxon = dendropy.Taxon(label=node.name)
    for child in node.enumerate_children():
        tree_node.add_child(process_node(child))
    return tree_node


def is_clade_template_name(name):
    return name.strip().casefold() == "clade" or name.strip().casefold() == "cladogram"


def get_clade_tree_from_wiki_page_string(wiki_page_string, index):
    wikicode = mwparserfromhell.parse(wiki_page_string, skip_style_tags=True)

    templates = wikicode.filter_templates(
        recursive=False, matches=lambda n: is_clade_template_name(n.name)
    )

    # We subtract one since the argument is 1-based
    template = templates[index - 1]

    if template.name.strip() == "cladogram":
        param_name = "clades" if template.has_param("clades") else "cladogram"
        template = template.get(param_name).value.filter_templates(recursive=False)[0]

    node = WikiCladeNode(None, template)
    tree = dendropy.Tree()
    tree.seed_node = process_node(node)
    return tree.as_string(schema="newick")


def get_clade_tree_from_wiki_page(wiki_title, index):
    wiki_string = get_text_from_wiki_page(wiki_title)

    return get_clade_tree_from_wiki_page_string(wiki_string, index)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", type=str, help="Wikipedia page title")
    parser.add_argument(
        "--wiki_file",
        type=str,
        help="Path to the pre-downloaded wiki file",
    )
    parser.add_argument(
        "index",
        type=int,
        nargs="?",
        default=1,
        help="Index of the cladogram within the page",
    )

    args = parser.parse_args()

    if args.wiki_file:
        with open(args.wiki_file) as f:
            wiki_string = f.read()
        print(get_clade_tree_from_wiki_page_string(wiki_string, args.index))
    else:
        print(get_clade_tree_from_wiki_page(args.title, args.index))


if __name__ == "__main__":
    main()
