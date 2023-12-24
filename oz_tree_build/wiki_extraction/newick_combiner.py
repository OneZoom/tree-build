import argparse
import dendropy

from oz_tree_build.wiki_extraction.wiki_extractor import get_taxon_tree_from_wiki_page


def find_node_by_taxon(tree, taxon):
    node = tree.find_node_with_taxon_label(taxon)
    if not node:
        node = tree.find_node_with_label(taxon)
    if not node:
        raise Exception(f"Could not find node for taxon '{taxon}'")
    return node


def insert_child_tree(parent_tree, child_tree, taxon, child_taxon, excluded_taxa):
    node_in_parent_tree = find_node_by_taxon(parent_tree, taxon)
    node_in_child_tree = find_node_by_taxon(child_tree, child_taxon)

    # Remove all excluded taxa from the child tree
    for excluded_taxon in excluded_taxa:
        node = find_node_by_taxon(child_tree, excluded_taxon)
        node.parent_node.remove_child(node)

    # We either replace the node, or add a child to it
    if child_taxon != taxon:
        node_in_parent_tree.add_child(node_in_child_tree)
    else:
        node_in_parent_tree.set_child_nodes(node_in_child_tree.child_nodes())


def process_file(filename, use_line_number_as_edge_length):
    main_tree = None
    for line_number, line in enumerate(open(filename)):
        # Ignore # comments
        if "#" in line:
            line = line[: line.index("#")]

        # Ignore blank lines
        line = line.strip()
        if line == "":
            continue

        tokens = line.split()

        # Lines look like:
        #   Dinosauria FROM Dinosaur@Taxonomy   # Taxomomy case
        #   Ornithischia FROM Ornithischia@1    # Cladogram case
        #   Ceratosauroidea->Ceratosauria FROM Ceratosauria@2   # Add a child instead of replacing the node
        if len(tokens) != 3:
            raise Exception(f"Invalid line: {line}")

        taxon = tokens[0]
        assert tokens[1] == "FROM"

        source = tokens[2]
        page_name, location = source.split("@")

        tree_string = get_taxon_tree_from_wiki_page(page_name, location)
        tree = dendropy.Tree.get(data=tree_string, schema="newick")

        if use_line_number_as_edge_length:
            # Go through all the nodes and set the edge lengths to be the line number.
            # This is useful for debugging. Add 1 to it, since editors are 1 based
            for node in tree.nodes():
                if node.label or node.taxon:
                    node.edge_length = line_number + 1

        if not main_tree:
            # main_tree = tree
            main_tree = dendropy.Tree()
            main_tree.seed_node = find_node_by_taxon(tree, taxon)
        else:
            if "->" in taxon:
                # Here, the child taxon is different from the parent taxon
                # e.g. "the_child->the_parent"
                child_taxon, taxon = taxon.split("->")
            else:
                child_taxon = taxon

            # Check for excluded taxa, e.g. "foo-bar-baz"
            parts = child_taxon.split("-")
            child_taxon = parts[0]
            excluded_taxa = parts[1:]

            # For the parent, only use the first part of the taxon, e.g. "foo"
            taxon = taxon.split("-")[0]

            insert_child_tree(main_tree, tree, taxon, child_taxon, excluded_taxa)

    return main_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "wikiclades_file",
        type=str,
        help="Path to the .wikiclades file",
    )
    parser.add_argument(
        "--use_line_number_as_edge_length",
        action="store_true",
        help="Use line number as edge length",
    )

    args = parser.parse_args()

    tree = process_file(args.wikiclades_file, args.use_line_number_as_edge_length)

    tree_string = tree.as_string(schema="newick")

    # This detects if we end up with duplicate taxon names
    tree2 = dendropy.Tree.get(data=tree_string, schema="newick")

    print(tree_string)

    # Print the number of nodes and leaves
    print(f"Tree has {len(tree.nodes())} nodes and {len(tree.leaf_nodes())} leaves")


if __name__ == "__main__":
    main()
