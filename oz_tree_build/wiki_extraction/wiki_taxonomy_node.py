import mwparserfromhell
from oz_tree_build.wiki_extraction.mwparserfromhell_helpers import (
    find_wikicode_node,
    get_taxon_name,
)


class WikiTaxonomyNode:
    @classmethod
    def create_root_node(
        cls, page_title, wikicode, header_title, taxon_to_page_mapping
    ):
        i, _ = find_wikicode_node(
            wikicode,
            0,
            mwparserfromhell.nodes.Heading,
            lambda node: node.title == header_title,
        )
        if i is None:
            raise Exception(f"Could not find header '{header_title}'")

        i, _ = find_wikicode_node(
            wikicode,
            i,
            mwparserfromhell.nodes.Tag,
            lambda node: node.wiki_markup == "*",
        )
        if i is None:
            raise Exception(f"Could not find '*' after header '{header_title}'")

        return cls.create_node(page_title, wikicode, i + 1, 0, taxon_to_page_mapping)

    @classmethod
    def create_node(cls, page_title, wikicode, index, depth, taxon_to_page_mapping):
        taxon = get_taxon_name(
            wikicode,
            start_index=index,
            page_title=page_title,
            taxon_to_page_mapping=taxon_to_page_mapping,
        )
        if not taxon:
            return None
        return cls(page_title, wikicode, index, depth, taxon)

    def __init__(self, page_title, wikicode, index, depth, taxon):
        self.page_title = page_title
        self.wikicode = wikicode
        self.index = index
        self.depth = depth
        self.taxon = taxon

    def enumerate_children(self, taxon_to_page_mapping):
        # Loop until we find get back to the starting depth
        i = self.index
        while True:
            # Find the next '*' heading
            i, node = find_wikicode_node(
                self.wikicode,
                i,
                mwparserfromhell.nodes.Tag,
                lambda node: node.wiki_markup == "*",
            )

            # If we didn't find one, we're done
            if i is None:
                return

            # Count the number of consecutive colons before the '*' heading
            colon_count = 0
            j = i - 1
            while (
                isinstance(self.wikicode.nodes[j], mwparserfromhell.nodes.Tag)
                and self.wikicode.nodes[j].wiki_markup == ":"
            ):
                colon_count += 1
                j -= 1

            # If the number of colons is less than the depth, we're done
            if colon_count <= self.depth:
                break

            # If it's not a direct child, skip it
            if colon_count > self.depth + 1:
                i += 1
                continue

            assert colon_count == self.depth + 1

            i += 1
            child_node = WikiTaxonomyNode.create_node(
                self.page_title, self.wikicode, i, self.depth + 1, taxon_to_page_mapping
            )
            if child_node:
                yield child_node
