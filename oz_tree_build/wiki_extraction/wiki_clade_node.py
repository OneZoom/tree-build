import re
import mwparserfromhell


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

    return taxon


def replace_spaces(s):
    return s.replace(" ", "_")


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


def is_clade_template_name(name):
    return name.strip().casefold() == "clade" or name.strip().casefold() == "cladogram"


class WikiCladeNode:
    @classmethod
    def create_root_node(cls, wikicode, cladogram_index):
        templates = wikicode.filter_templates(
            recursive=False, matches=lambda n: is_clade_template_name(n.name)
        )

        # We subtract one since the argument is 1-based
        template = templates[cladogram_index - 1]

        if template.name.strip() == "cladogram":
            param_name = "clades" if template.has_param("clades") else "cladogram"
            template = template.get(param_name).value.filter_templates(recursive=False)[
                0
            ]

        return WikiCladeNode(None, template)

    def __init__(self, taxon, template=None, subclades=None):
        self.taxon = taxon

        # Get the subclades if not passed in, which happens at the root node
        if template and not subclades:
            subclades = {}
            for i in range(65, 91):
                if template.has_param(f"target{chr(i)}"):
                    subclade_token_name = str(
                        template.get(f"target{chr(i)}").value
                    ).strip()
                    subclades[subclade_token_name] = template.get(
                        f"subclade{chr(i)}"
                    ).value
                else:
                    break

        self.template = template
        self.subclades = subclades

    def enumerate_children(self):
        if not self.template:
            return

        # Loop through the numeric parameters, e.g. |1, |2, ...
        for p in self.template.params:
            param_name = p.name.strip()
            if not param_name.isnumeric():
                continue

            sub = p.value

            # If there is a matching subclade (e.g. {CYNOGNATHIA}), use that instead
            if sub.strip() in self.subclades:
                sub = self.subclades[sub.strip()]

            sub_templates = sub.filter_templates(
                recursive=False, matches=lambda n: n.name.lower().startswith("clade")
            )

            taxon = ""

            # If there is a label parameter, use that
            if self.template.has_param(f"label{param_name}"):
                taxon = (
                    get_taxon_name(self.template.get(f"label{param_name}").value) or ""
                )

            if len(sub_templates) == 0:
                # Leaf node case (no sub-template)
                taxon = taxon or get_taxon_name(sub)
                if not taxon:
                    continue
                yield WikiCladeNode(taxon)
            else:
                assert len(sub_templates) == 1, "Only one sub-template allowed"
                yield WikiCladeNode(taxon, sub_templates[0], self.subclades)
