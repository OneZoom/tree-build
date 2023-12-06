"""
Check if a tree is ultrametric, and if not, print the details of the non-ultrametricity
"""

import argparse
import dendropy
import os


def get_taxon_name(node):
    if node.taxon:
        return node.taxon.label

    if not node.parent_node:
        return "Root"

    if len(node.child_nodes()) > 0:
        return f"(Unnamed node)"

    # If there's no taxon, it's probably an extinct prop-up node,
    # and we get the name from the parent node
    return f"{node.parent_node.label} (Extinct)"


def check_ultrametricity(tree, print_details=False):
    known_age = None
    initial_name = None
    non_ultrametric_message = None
    edge_lengths = []
    age_instances = {}

    def process_node(node):
        nonlocal known_age, initial_name, non_ultrametric_message

        name = get_taxon_name(node)

        # Ignore nested files, which will never look ultrametric within this file
        if name.endswith("@"):
            return

        # If it's a leaf node, process it
        if len(node.child_nodes()) == 0:
            age = round(sum(edge_lengths), 12)

            # If it's the first one we see, record its age and name
            if not known_age:
                known_age = age
                initial_name = name
            elif not non_ultrametric_message:
                # For other leaves, check that they have the same age. If not, record the error
                if known_age != age:
                    non_ultrametric_message = f"Not ultrametric! {name} has age {age}, but {initial_name} has age {known_age}"

            if print_details:
                print(f"{name}: {age}={'+'.join([str(x) for x in edge_lengths])}")

            # Count the number of times this age occurs
            if age not in age_instances:
                age_instances[age] = 0
            age_instances[age] += 1
        else:
            # If it's not a leaf node, recurse into its children
            for child in node.child_node_iter():
                # Treat None as 0
                # REVIEW: Is this correct? Should it be an error?
                edge_lengths.append(child.edge_length or 0)
                process_node(child)
                edge_lengths.pop()

    process_node(tree)

    if print_details:
        # Dump the age counts in descending order of count
        print(f"Age counts instances ({len(age_instances)} variants): {age_instances}")

    if non_ultrametric_message:
        print(non_ultrametric_message)

    return not non_ultrametric_message


def process_file(file_path, print_details):
    print("====== " + os.path.basename(file_path))

    tree = dendropy.Tree.get(path=file_path, schema="newick")

    check_ultrametricity(tree.seed_node, print_details)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print_details",
        action="store_true",
        help="Print detailed age information for each leaf",
    )
    parser.add_argument("newick_files", nargs="+")
    args = parser.parse_args()

    for file in args.newick_files:
        process_file(file, args.print_details)


if __name__ == "__main__":
    main()
