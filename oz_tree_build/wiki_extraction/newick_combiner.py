import dendropy

from oz_tree_build.wiki_extraction.wiki_extractor import get_clade_tree_from_wiki_page


def find_node(tree, taxon):
    node = tree.find_node_with_taxon_label(taxon)
    if not node:
        node = tree.find_node_with_label(taxon)
    if not node:
        raise Exception(f"Could not find node for taxon '{taxon}'")
    return node


def insert_child_tree(parent_tree, child_tree, taxon):
    node_in_parent_tree = find_node(parent_tree, taxon)
    node_in_child_tree = find_node(child_tree, taxon)

    node_in_parent_tree.set_child_nodes(node_in_child_tree.child_nodes())


def process_file(filename):
    main_tree = None
    for line in open(filename):
        line = line.strip()
        if line == "" or line.startswith("#"):
            continue

        tokens = line.split()

        page_name = tokens[0]
        index = int(tokens[1]) if len(tokens) > 1 else 1
        clade = tokens[2] if len(tokens) > 2 else page_name
        tree_string = get_clade_tree_from_wiki_page(page_name, index)
        tree = dendropy.Tree.get(data=tree_string, schema="newick")

        if not main_tree:
            # main_tree = tree
            main_tree = dendropy.Tree()
            main_tree.seed_node = find_node(tree, clade)
        else:
            insert_child_tree(main_tree, tree, clade)

    return main_tree


# tree = process_file("data/OZTreeBuild/ExtinctSpecies/Dinosauria.wikiclades")
tree = process_file("data/OZTreeBuild/ExtinctSpecies/Synapsida.wikiclades")
print(tree.as_string(schema="newick"))
