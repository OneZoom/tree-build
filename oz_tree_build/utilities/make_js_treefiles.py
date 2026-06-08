import argparse
import fileinput
import json
import os
import re
import shutil
from subprocess import call


# string -> string
# Given newick filepath(string), return a string without comma and semi comma
# Input: '../../data/output_files/ordered_tree_test.nwk' -> '((,),)'
# Output: '(())'
def tidy_newick(newick_filepath):
    res = ""
    for line in fileinput.input(files=(newick_filepath)):
        res += line.replace(",", "").replace(";", "").replace("\n", "")
    return res


# String -> String
# Given tidied newick string, return rawData in completetree.js
# Input: (())
# Output:var rawData = '(())';
def generate_completetree_js(newick_str):
    return "var rawData = '" + newick_str + "';"


# String, Number -> String
# Given tidied newick(polytomy) string, return stringified cut position map for
# binary tree and polytomy tree
def generate_cut_position_map(newick_str, threshold):
    binary_cut_map = generate_binary_cut_position_map(newick_str, threshold)
    polytomy_cut_map = generate_polytomy_cut_position_map(newick_str, threshold)
    cut_threshold = "var cut_threshold = " + str(threshold) + ";"
    return binary_cut_map + "\n\n" + polytomy_cut_map + "\n\n" + cut_threshold


# String, Number -> String
# Given tidied newick string, return stringified cut_position_map object.
# Output example:
# '{
#   "4203700":1302201,"4203701":685684,"4203702":685609,"4203703":683568,
#   "4203704":7901,"4203705":7900,"4203706":6417,"4203707":6396
# }'
def generate_binary_cut_position_map(newick_str, threshold):
    count_arr = [None] * len(newick_str)
    count = 0
    for index, c in enumerate(reversed(newick_str)):
        index = len(newick_str) - index - 1
        if c == "(" or c == "{":
            count = count - 1
        elif c == ")" or c == "}":
            count = count + 1
        else:
            raise ValueError("newick str contains non bracket character: " + c)
        count_arr[index] = count

    start_end_arr = [0, len(count_arr) - 1]
    cut_position_map = {}
    while len(start_end_arr) > 0:
        start = start_end_arr.pop(0)
        end = start_end_arr.pop(0)
        build_cut_position_map(start, end, start_end_arr, count_arr, cut_position_map, threshold)
    cut_position_map = json.dumps(cut_position_map)
    cut_position_map = "var cut_position_map_json_str = '" + cut_position_map + "';"
    return cut_position_map


# String, Number -> String
# Given tidied newick(polytomy) string, return stringified cut_position_map object.
# Output example:
# '{
#   "4203700":{685684, 79999, 1302201, 4203701},
#   "4203702":{685609, 4203703},
#   "4203704": {7901,4203705,7900,4203706}
# }'
# The key of the output json string is the end position of a string in the newick_str, the
# value is an array: [start_sub1, end_sub1, start_sub2, end_sub2, ..., start_subN, end_subN].
# start_subN is the start pos of its nth child, end_subN is the end pos of its nth child.
def generate_polytomy_cut_position_map(newick_str, threshold):
    start_end_arr = [0, len(newick_str) - 1]
    cut_position_map = {}
    while len(start_end_arr) > 0:
        start = start_end_arr.pop(0)
        end = start_end_arr.pop(0)
        cut_position_map[end] = get_polytomy_substring_pos(start, end, start_end_arr, threshold, newick_str)
    cut_position_map = json.dumps(cut_position_map)
    cut_position_map = "var polytomy_cut_position_map_json_str = '" + cut_position_map + "';"
    return cut_position_map


# Number, Number, Array, Array, Map, Number
# start, end represent indices of a node A on rawData.
# this function finds cut position of node A on rawData, then store it in cut_position_map
# and put its children start and end position in start_end_arr
def build_cut_position_map(start, end, start_end_arr, count_arr, cut_position_map, threshold):
    endValue = count_arr[end]
    for index in reversed(range(start, end)):
        if count_arr[index] == endValue:
            cut_position_map[end] = index - 1
            if (index - start - 2) >= threshold:
                start_end_arr.append(start + 1)
                start_end_arr.append(index - 1)
            if (end - index - 1) >= threshold:
                start_end_arr.append(index)
                start_end_arr.append(end - 1)
            break


# Find substring start & end position given a string representing a polytomous tree.
# The start and end position is pushed into start_end_arr if its distance is > than threshold
def get_polytomy_substring_pos(start, end, start_end_arr, threshold, newick_str, called_by_self=False):
    res = []
    if end <= start or (called_by_self and newick_str[end] == ")"):
        res += [start, end]
        if (end - start) > threshold:
            start_end_arr.append(start)
            start_end_arr.append(end)
        return res

    cut_point = None
    bracket_count = 0
    for index in reversed(range(start, end + 1)):
        c = newick_str[index]
        if c == ")" or c == "}":
            bracket_count = bracket_count + 1
        elif c == "(" or c == "{":
            bracket_count = bracket_count - 1
            if bracket_count == 1:
                cut_point = index - 1
                break
    if cut_point is not None:
        res = res + get_polytomy_substring_pos(start + 1, cut_point, start_end_arr, threshold, newick_str, True)
        res = res + get_polytomy_substring_pos(cut_point + 1, end - 1, start_end_arr, threshold, newick_str, True)
    else:
        res += [start, start, end, end]
    return res


def write_js_file(outdir, input_path, version_number, args):
    # Output to versioned path
    input_name = os.path.basename(input_path)
    output_path = os.path.join(
        outdir,
        re.sub(
            # Extract any existing version number / extension from filename
            r"(_\d+)?(\.[a-zA-Z]+)$",
            # Replace with verison number / extension
            "_" + str(version_number) + r"\2",
            input_name,
        ),
    )

    if input_name.startswith("ordered_tree_"):
        output_path = re.sub(r"ordered_tree_", "completetree_", output_path)
        output_path = re.sub(r"\.(nwk|poly)$", ".js", output_path)

        print(f"{input_path} -> {output_path}")
        newick_str = tidy_newick(input_path)
        with open(output_path, "w") as out_f:
            out_f.write(generate_completetree_js(newick_str))

        # Generate derived cut-position-map
        cut_path = re.sub(r"completetree_", r"cut_position_map_", output_path)
        with open(cut_path, "w") as out_f:
            out_f.write(generate_cut_position_map(newick_str, args.threshold))
        # Trigger write_js_file for cut map so we gzip it
        write_js_file(outdir, cut_path, version_number, args)

    elif input_path == output_path:
        # Nothing to do, already in output_path
        pass
    else:
        # By default we just copy file
        print(f"{input_path} -> {output_path}")
        shutil.copyfile(input_path, output_path)
    print(f"{output_path} -> {output_path}.gz")
    call(["gzip", "-9fk", output_path])


def main():
    # rawData string + metadata -> output result into file.

    # produce cut_position_map.js and completetree.js given newick tree.
    parser = argparse.ArgumentParser(
        description="Generate rawData, metadata and cut_position_map given newick string",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # pick the most recent ordered_tree_XXX.nwk file
    import re

    parser.add_argument(
        "--outdir",
        "-o",
        default=os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "OZtree",
            "static",
            "FinalOutputs",
            "data",
        ),
        help="output filepath of cut_position_map",
    )
    parser.add_argument(
        "in_files",
        nargs="+",
        metavar="FILE",
        help="Files to move to outdir, with versions appended if not present",
    )
    parser.add_argument(
        "--threshold",
        default=10000,
        type=int,
        help=("Threshold for deciding if a node and its descendants needs to be" "recorded in cut_position_map"),
    )
    parser.add_argument(
        "--version",
        type=int,
        help=("Version number / serial to append to file names, if not provided assume present on at least one file"),
    )

    args = parser.parse_args()

    if args.version:
        version_number = args.version
    else:
        # Find higest version number in files present, use that as version
        version_number = 0
        for f in args.in_files:
            m = re.search(r"_(\d+)\.(\w+)$", f)
            if m and int(m.group(1)) > version_number:
                version_number = int(m.group(1))

    for f in args.in_files:
        write_js_file(args.outdir, f, version_number, args)

    print("Done")


if __name__ == "__main__":
    main()
