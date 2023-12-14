# https://en.wikipedia.org/wiki/Template:Clade documents the clade template design

import argparse
import mwparserfromhell
import requests_cache

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


def parse_wiki_page(title):
    return mwparserfromhell.parse(get_text_from_wiki_page(title), skip_style_tags=True)


# def get_fossil_range(title):
#     wikicode = parse_wiki_page(title)
#     templates = wikicode.filter_templates()
#     for template in templates:
#         if template.name.matches("Automatic taxobox"):
#             return template.get("fossil_range").value.strip()
#     return None


def clean_string(s):
    s = s.strip().strip("[]()'" "†? ")

    # If the string contains anything other than letters, numbers, or spaces, return an empty string
    if not s.replace(" ", "").isalnum():
        return ""

    return s


def replace_spaces(s):
    return s.replace(" ", "_")


def get_taxon_name(wikicode):
    for node in wikicode.nodes:
        clean_node_string = clean_string(node)
        if clean_node_string == "":
            continue

        if isinstance(node, mwparserfromhell.nodes.wikilink.Wikilink):
            return str(node.text) if node.text else str(node.title)

        if isinstance(node, mwparserfromhell.nodes.text.Text):
            return clean_node_string

    return None


def convert_wiki_template_to_newick_string_nested(template, subclades, top_level=True):
    newick = ""

    need_braces = not top_level or template.has_param(2)
    if need_braces:
        newick += "("

    # Loop through the numeric parameters, e.g. |1, |2, ...
    for p in template.params:
        param_name = p.name.strip()
        if not param_name.isnumeric():
            continue

        sub = p.value

        # If there is a matching subclade (e.g. {CYNOGNATHIA}), use that instead
        if sub.strip() in subclades:
            sub = subclades[sub.strip()]

        sub_templates = sub.filter_templates(
            recursive=False, matches=lambda n: n.name.lower().startswith("clade")
        )

        taxon = ""

        # If there is a label parameter, use that
        if template.has_param(f"label{param_name}"):
            taxon = get_taxon_name(template.get(f"label{param_name}").value) or ""

        if len(sub_templates) == 0:
            # Leaf node case (no sub-template)
            taxon = taxon or get_taxon_name(sub)
            if not taxon:
                continue
        else:
            assert len(sub_templates) == 1, "Only one sub-template allowed"
            newick += convert_wiki_template_to_newick_string_nested(
                sub_templates[0], subclades, top_level=False
            )

        newick += replace_spaces(taxon)
        newick += ","

    # Remove the last comma, if there is one
    newick = newick.rstrip(",")
    if need_braces:
        newick += ")"
    return newick


def convert_wiki_template_to_newick_string(template):
    # Loop from 'A' to 'Z' to look for subclades. e.g.
    #   |targetA ={CYNOGNATHIA}
    #   |subcladeA={{ ... }}
    subclades = {}
    for i in range(65, 91):
        if template.has_param(f"target{chr(i)}"):
            subclade_token_name = str(template.get(f"target{chr(i)}").value).strip()
            subclades[subclade_token_name] = template.get(f"subclade{chr(i)}").value
        else:
            break

    return convert_wiki_template_to_newick_string_nested(template, subclades)


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

    return convert_wiki_template_to_newick_string(template) + ";"


def get_clade_tree_from_wiki_page(wiki_title, index):
    wiki_string = get_text_from_wiki_page(wiki_title)

    return get_clade_tree_from_wiki_page_string(wiki_string, index)


# path = os.path.join(os.path.dirname(__file__), "test.wiki")

# text = get_text_from_wiki_page("Spinosauridae")

# with open(path, "w") as f:
#     f.write(text)


# Read the file test.wiki, in the same folder as this script
# with open(path) as f:
#     wikicode = mwparserfromhell.parse(f.read(), skip_style_tags=True)


# wikicode = parse("Spinosauridae")
# wikicode = parse("Carnosauria")
# wikicode = parse("Dicynodont")


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
