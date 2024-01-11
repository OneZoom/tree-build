"""
Format a newick tree with indentation to make it more human readable

For example, if the input tree is:
(Tupaia_tana:8.5,(Tupaia_picta:8.0,(Tupaia_montana:7.0,Tupaia_splendidula:7.0):1.0):0.5):4.5;
The output is:
(
  Tupaia_tana:8.5,
  (
    Tupaia_picta:8.0,
    (
      Tupaia_montana:7.0,
      Tupaia_splendidula:7.0
    ):1.0
  ):0.5
):4.5;

This is not used directly by OneZoom, but is a useful general purpose utility.
"""

import argparse
import re
import sys

from oz_tree_build.tree_build.build_oz_tree import trim_tree

__author__ = "David Ebbo"

# Token may be quoted or not
whole_token_regex = re.compile("('[^']*'|[^(),;[]+)(:[0-9.]+)?")


def format_nwk(newick_tree, output_stream, indent_spaces=2):
    newick_tree = trim_tree(newick_tree, strip_semicolon=False)

    indent_string = " " * indent_spaces

    index = 0
    depth = 0

    while index < len(newick_tree):
        # If we've reached a new branch, write the opening brace and increase the depth
        if newick_tree[index] == "(":
            index += 1
            output_stream.write(indent_string * depth)
            output_stream.write("(\n")
            depth += 1
            continue

        # If we've reached the end of a branch, write the closing brace and decrease the depth
        closed_brace = newick_tree[index] == ")"
        if closed_brace:
            index += 1
            depth -= 1
            output_stream.write("\n")
            output_stream.write(indent_string * depth)
            output_stream.write(")")

        # If we've reached a token, write it out
        if match_full_name := whole_token_regex.match(newick_tree, index):
            index = match_full_name.end()
            if not closed_brace:
                output_stream.write(indent_string * depth)
            output_stream.write(match_full_name.group())

            # If the token is followed by a comment, write it out
            # Note that we only support comments at the end of a token
            if newick_tree[index] == "[":
                end_comment_index = newick_tree.index("]", index)
                output_stream.write(newick_tree[index : end_comment_index + 1])
                index = end_comment_index + 1

        # If we've reached a comma, write it out and start a new line
        if newick_tree[index] == ",":
            output_stream.write(",\n")
            index += 1

        # If we've reached the end of the tree, write the semicolon and break
        if newick_tree[index] == ";":
            output_stream.write(newick_tree[index] + "\n")
            break


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "treefile",
        type=argparse.FileType("r"),
        nargs="?",
        default=sys.stdin,
        help="The tree file in newick format",
    )
    parser.add_argument(
        "outputfile",
        type=argparse.FileType("w"),
        nargs="?",
        default=sys.stdout,
        help="The output tree file",
    )
    parser.add_argument(
        "--indent_spaces",
        "-i",
        default=2,
        type=int,
        help="the number of spaces for each indentation level",
    )
    args = parser.parse_args()
    format_nwk(args.treefile.read(), args.outputfile, args.indent_spaces)


if __name__ == "__main__":
    main()
