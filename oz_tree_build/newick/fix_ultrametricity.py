"""
Fix a tree to become ultrametric, by adjusting the leaf lengths to add up to the expected age.
"""

import argparse
import dendropy

from oz_tree_build.newick.check_ultrametricity import get_taxon_name


def fix_ultrametricity(tree, expected_age, max_adjustment):
    def process_node(node, age_so_far):
        name = get_taxon_name(node)

        # Ignore nested files, which will never look ultrametric within this file
        if name.endswith("@"):
            return

        if len(node.child_nodes()) == 0:
            # If it's a leaf node, adjust its edge length to make the total age correct
            if age_so_far != expected_age:
                # If the absolute difference is too large, raise an error
                if abs(age_so_far - expected_age) > max_adjustment:
                    raise Exception(
                        f"{name} has age {age_so_far}, which is {abs(age_so_far - expected_age)} from {expected_age} (max allowed delta is {max_adjustment}))"
                    )

                node.edge_length = round(
                    node.edge_length + expected_age - age_so_far, 6
                )
        else:
            # If it's not a leaf node, recurse into its children
            for child in node.child_node_iter():
                # If the child has an edge length, round it to 6 decimal places
                if child.edge_length is not None:
                    child.edge_length = round(child.edge_length, 6)

                process_node(child, age_so_far + (child.edge_length or 0))

    process_node(tree.seed_node, 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "treefile",
        type=argparse.FileType("r"),
        nargs="?",
        help="The tree file in newick format",
    )
    parser.add_argument("age", type=float, help="Expected length")
    parser.add_argument(
        "max_adjustment",
        type=float,
        default="0.000005",
        nargs="?",
        help="The largest leaf age adjustment allowed",
    )
    args = parser.parse_args()

    tree = dendropy.Tree.get(file=args.treefile, schema="newick")
    fix_ultrametricity(tree, args.age, args.max_adjustment)

    adjusted_tree_string = tree.as_string(
        schema="newick",
        suppress_leaf_node_labels=False,
        unquoted_underscores=True,
        suppress_rooting=True,
    )

    print(adjusted_tree_string)


if __name__ == "__main__":
    main()
