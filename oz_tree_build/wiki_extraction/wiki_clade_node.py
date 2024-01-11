"""
https://en.wikipedia.org/wiki/Template:Clade documents the clade template design
"""

import logging
from oz_tree_build.wiki_extraction.mwparserfromhell_helpers import (
    get_taxon_and_page_title,
)


def is_clade_template_name(name):
    return name.strip().casefold() == "clade" or name.strip().casefold() == "cladogram"


class WikiCladeNode:
    @classmethod
    def create_root_node(cls, containing_page_title, wikicode, cladogram_index):
        templates = wikicode.filter_templates(
            recursive=False, matches=lambda n: is_clade_template_name(n.name)
        )

        # We may not find it with recursive=False, e.g. if it's nested in a <div></div>
        # Passing recursive=True is probamatic, as it will find all nested clade templates,
        # so we can only do this if we're looking for the very first cladogram
        # TODO: solve the general case
        if len(templates) == 0 and cladogram_index == 1:
            templates = wikicode.filter_templates(
                recursive=True, matches=lambda n: is_clade_template_name(n.name)
            )
            if len(templates) > 0:
                logging.warning(
                    f"Found cladogram with recursive=True, but it was nested"
                )

        # We subtract one since the argument is 1-based
        template = templates[cladogram_index - 1]

        # If the template is wrapped in a {{cladogram}} template, use the inner clade template
        if template.name.strip().casefold() == "cladogram".casefold():
            param_name = "clades" if template.has_param("clades") else "cladogram"
            template = template.get(param_name).value.filter_templates(recursive=False)[
                0
            ]

        return WikiCladeNode(containing_page_title, None, None, template)

    def __init__(
        self,
        containing_page_title,
        taxon,
        taxon_page_title,
        template=None,
        subclades=None,
    ):
        self.containing_page_title = containing_page_title
        self.taxon = taxon
        self.taxon_page_title = taxon_page_title
        self.template = template

        # Get the subclades if not passed in, which happens at the root node
        # See https://en.wikipedia.org/wiki/Template:Clade#Using_subtrees
        if template and not subclades:
            subclades = {}
            # Look for targets, e.g. |targetA=, |targetB=, ...
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
            child_is_leaf = len(sub_templates) == 0

            taxon = taxon_page_title = ""

            # If there is a label parameter, use that
            if self.template.has_param(f"label{param_name}"):
                taxon, taxon_page_title = get_taxon_and_page_title(
                    self.template.get(f"label{param_name}").value,
                    link_only=child_is_leaf,
                )

            if child_is_leaf:
                # Leaf node case (no sub-template)
                if not taxon:
                    taxon, taxon_page_title = get_taxon_and_page_title(
                        sub,
                        link_only=True,
                        containing_page_title=self.containing_page_title,
                    )
                if not taxon:
                    continue
                yield WikiCladeNode(self.containing_page_title, taxon, taxon_page_title)
            else:
                assert len(sub_templates) == 1, "Only one sub-template allowed"
                yield WikiCladeNode(
                    self.containing_page_title,
                    taxon,
                    taxon_page_title,
                    sub_templates[0],
                    self.subclades,
                )
