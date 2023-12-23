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


def process_file(filename):
    main_tree = None
    for line in open(filename):
        line = line.strip()
        if line == "" or line.startswith("#"):
            continue

        tokens = line.split()

        page_name = tokens[0]
        taxonomy_header = cladogram_index = None
        if len(tokens) > 1:
            if tokens[1].startswith("@"):
                taxonomy_header = tokens[1][1:]
            else:
                cladogram_index = int(tokens[1])
        if not taxonomy_header and not cladogram_index:
            cladogram_index = 1
        clade = tokens[2] if len(tokens) > 2 else page_name
        tree_string = get_clade_tree_from_wiki_page(
            page_name, cladogram_index, taxonomy_header
        )
        tree = dendropy.Tree.get(data=tree_string, schema="newick")

        if not main_tree:
            # main_tree = tree
            main_tree = dendropy.Tree()
            main_tree.seed_node = find_node_by_taxon(tree, clade)
        else:
            insert_child_tree(main_tree, tree, clade)

    return main_tree


# tree = process_file("data/OZTreeBuild/ExtinctSpecies/Dinosauria.wikiclades")
tree = process_file("data/OZTreeBuild/ExtinctSpecies/Synapsida.wikiclades")
print(tree.as_string(schema="newick"))
