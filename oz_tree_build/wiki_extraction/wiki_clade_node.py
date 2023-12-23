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


def get_taxon_name(wikicode):
    for node in wikicode.nodes:
        if isinstance(node, mwparserfromhell.nodes.wikilink.Wikilink):
            taxon = str(node.text) if node.text else str(node.title)
        elif isinstance(node, mwparserfromhell.nodes.text.Text):
            taxon = node.value
        else:
            # Ignore all other types, e.g. HTMLEntity
            continue

        # This may return None if the taxon name is not usable
        taxon = validate_clean_taxon(taxon)
        if taxon:
            return taxon

    return None


class WikiCladeNode:
    def __init__(self, name, template=None, subclades=None):
        self.name = name

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
