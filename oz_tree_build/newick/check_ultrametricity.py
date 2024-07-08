"""
Check if a tree is ultrametric, and if not, print the details of the non-ultrametricity
"""

import argparse
import os

import dendropy


def get_taxon_name(node):
    if node.taxon:
        return node.taxon.label

    if not node.parent_node:
        return "Root"

    if len(node.child_nodes()) > 0:
        return "(Unnamed node)"

    # If there's no taxon, it's probably an extinct prop-up node,
    # and we get the name from the parent node
    return f"{node.parent_node.label} (Extinct)"


def check_ultrametricity(tree, print_details=False):
    known_total_length = None
    initial_name = None
    non_ultrametric_message = None
    edge_lens = []
    age_instances = {}

    def process_node(node):
        nonlocal known_total_length, initial_name, non_ultrametric_message

        name = get_taxon_name(node)

        # Ignore nested files, which will never look ultrametric within this file
        if name.endswith("@"):
            return

        if len(node.child_nodes()) == 0:
            # It's a leaf node

            # If the edge length is None, it's unknown, so we can't check ultrametricity
            if node.edge_length is None:
                return

            # We round up to 10 decimal places, to avoid floating point errors
            total_length = round(sum(edge_lens), 10)

            # If it's the first one we see, record its total length and name
            if not known_total_length:
                known_total_length = total_length
                initial_name = name
            elif not non_ultrametric_message:
                # For other leaves, check they have the same total length
                if known_total_length != total_length:
                    non_ultrametric_message = (
                        f"Not ultrametric! {name} has length {total_length}, "
                        f"but {initial_name} has length {known_total_length}"
                    )

            if print_details:
                print(f"{name}: {total_length}={'+'.join([str(x) for x in edge_lens])}")

            # Count the number of times this length occurs
            if total_length not in age_instances:
                age_instances[total_length] = 0
            age_instances[total_length] += 1
        else:
            # If it's not a leaf node, recurse into its children
            for child in node.child_node_iter():
                # Treat None as 0
                # REVIEW: Is this correct? Should it be an error?
                edge_lens.append(child.edge_length or 0)
                process_node(child)
                edge_lens.pop()

    process_node(tree.seed_node)

    # Dump the instance count for each total length
    print(f"Age counts instances ({len(age_instances)} variants): {age_instances}")

    if non_ultrametric_message:
        print(non_ultrametric_message)

    return not non_ultrametric_message


def process_file(file_path, print_details):
    print(f"====== {os.path.basename(file_path)} ======")

    tree = dendropy.Tree.get(path=file_path, schema="newick")

    check_ultrametricity(tree, print_details)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print_details",
        action="store_true",
        help="Print detailed edge length information for each leaf",
    )
    parser.add_argument("newick_files", nargs="+")
    args = parser.parse_args()

    for file in args.newick_files:
        process_file(file, args.print_details)


if __name__ == "__main__":
    main()
