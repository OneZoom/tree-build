import argparse
import dendropy

from oz_tree_build.wiki_extraction.wiki_extractor import get_clade_tree_from_wiki_page


def find_node_by_taxon(tree, taxon):
    node = tree.find_node_with_taxon_label(taxon)
    if not node:
        node = tree.find_node_with_label(taxon)
    if not node:
        raise Exception(f"Could not find node for taxon '{taxon}'")
    return node


def insert_child_tree(parent_tree, child_tree, taxon):
    node_in_parent_tree = find_node_by_taxon(parent_tree, taxon)
    node_in_child_tree = find_node_by_taxon(child_tree, taxon)

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
        if len(tokens) != 3:
            raise Exception(f"Invalid line: {line}")

        clade = tokens[0]
        assert tokens[1] == "FROM"

        source = tokens[2]
        page_name, location = source.split("@")

        tree_string = get_clade_tree_from_wiki_page(page_name, location)
        tree = dendropy.Tree.get(data=tree_string, schema="newick")

        if use_line_number_as_edge_length:
            # Go through all the nodes and set the edge lengths to be the line number (for debugging)
            for node in tree.nodes():
                if node.label or node.taxon:
                    node.edge_length = line_number

        if not main_tree:
            # main_tree = tree
            main_tree = dendropy.Tree()
            main_tree.seed_node = find_node_by_taxon(tree, clade)
        else:
            insert_child_tree(main_tree, tree, clade)

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

    print(tree_string)

    # Print the number of nodes and leaves
    print(f"Tree has {len(tree.nodes())} nodes and {len(tree.leaf_nodes())} leaves")


if __name__ == "__main__":
    main()
