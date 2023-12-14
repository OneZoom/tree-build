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


# tree1 = dendropy.Tree.get(data="(A:1,B:1,(C:1,D:1)E:1)F;", schema="newick")
# tree2 = dendropy.Tree.get(data="(G,H)I;", schema="newick")

# tree1.seed_node.add_child(tree2.seed_node)
# tree1.seed_node.child_nodes()[2].add_child(tree2.seed_node)

# node = tree1.find_node_with_label("D")
# node = tree1.find_node_for_taxon("D")

# s = "E"
# node = tree1.find_node_with_taxon(lambda taxon: taxon.label == s)


# print(tree1.as_ascii_plot())
# print(tree1.as_string(schema="newick"))

# tree1_string = get_clade_tree_from_wiki_page("Ornithischia", 1)
# tree1 = dendropy.Tree.get(data=tree1_string, schema="newick")

# tree2_string = get_clade_tree_from_wiki_page("Stegosauria", 2)
# tree2 = dendropy.Tree.get(data=tree2_string, schema="newick")
# insert_child_tree(tree1, tree2, "Stegosauria")

# tree2_string = get_clade_tree_from_wiki_page("Talenkauen", 1)
# tree2 = dendropy.Tree.get(data=tree2_string, schema="newick")
# insert_child_tree(tree1, tree2, "Elasmaria")

# print(tree1.as_string(schema="newick"))

tree = process_file("data/OZTreeBuild/ExtinctSpecies/Dinosauria.wikiclades")
# tree = process_file("data/OZTreeBuild/ExtinctSpecies/Synapsida.wikiclades")
print(tree.as_string(schema="newick"))
