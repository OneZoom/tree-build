"""
Go through all the bespoke files and generate an html fragment with the list of DOI links
in each file. See https://github.com/OneZoom/tree-build/issues/42 for more details

e.g. from the root of the repo, run:
python oz_tree_build/utilities/generate_bespoke_doi_html.py \
    data/OZTreeBuild/AllLife/BespokeTree/include_noAutoOTT
"""

import argparse
import os
import re

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "bespoke_files_folder",
    type=str,
    help="Path to the folder containing the bespoke .phi files",
)
args = parser.parse_args()
directory_path = args.bespoke_files_folder

clade_regex = re.compile(r"\)([a-zA-Z0-9_]+)(_ott[0-9]+)?(:[0-9\.]+)?;")
doi_regex = re.compile(r"https://doi.org/[a-zA-Z0-9\-_\.\/]*")

html_content = "<ul>\n"
# Iterate through all the files in the directory
file_list = sorted(os.listdir(directory_path))
for filename in file_list:
    file_path = os.path.join(directory_path, filename)
    with open(file_path) as file:
        file_contents = file.read()

        doi_links = re.findall(doi_regex, file_contents)
        # Skip files with no DOI links
        if not doi_links:
            continue

        # Find the last clade name in the file (i.e. the last thing in the newick)
        clade_search = re.findall(clade_regex, file_contents)
        if clade_search:
            clade_name = clade_search[-1][0]
            html_content += (
                "  <li><a href='https://www.onezoom.org/life/"
                f"@{clade_name}'>{clade_name}</a></li>\n"
            )
        else:
            # Some newicks don't have a final clade name, so just use the filename instead
            filename_without_extension = os.path.splitext(filename)[0]
            html_content += f"  <li>{filename_without_extension}</li>\n"

        # Create a sub-list of all the DOI links in the file
        html_content += "  <ul>\n"
        for doi_link in doi_links:
            html_content += f"    <li><a href='{doi_link}'>{doi_link}</a></li>\n"
        html_content += "  </ul>\n"

html_content += "</ul>\n"

print(html_content)
