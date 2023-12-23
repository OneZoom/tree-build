from oz_tree_build.wiki_extraction.mwparserfromhell_helpers import get_taxon_name


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
