__author__ = "David Ebbo"

import logging
import os.path
import re

from .token_to_oz_tree_file_mapping import token_to_file_map

__author__ = "David Ebbo"

full_ott_token = re.compile(r"'?([\w\-~]+)@'?(?::([\d\.]+))?")
ott_details = re.compile(r"(\w+)_ott(\d*)~?([-\d]*)$")


def enumerate_one_zoom_tokens(tree, ot_parts_folder=None, oz_parts_folder=None):
    """
    Enumerates all the OneZoom tokens in a tree string (e.g. foobar_ott123~-789-111)

    Yields dicts with the keys:

    - start: Position in in string the match was found
    - end: End of match
    - node_name_in_parent: Node name from inclusion node, ignoring OZ inclusion syntax
    - edge_length_in_parent: Edge length from inclusion node
    - file: File path pointing to tree to substitute
    - base_ott: OTT of root, if subtree is a OT tree
    - excluded_otts: OTTs to exclude from subtree
    - expand_nodes: Should we recurse and apply OZ inclusion rules to subtree?
    - override_edge_length: Replace edge length from root node with this value
    - override_taxon: Replace root node name with this value
    """

    # Skip the comment block at the start of the file
    start_index = tree.index("]") if "[" in tree else 0

    for full_match in full_ott_token.finditer(tree, start_index):
        result = {
            "start": full_match.start(),
            "end": full_match.end(),
            "node_name_in_parent": full_match.group(1),
            "edge_length_in_parent": float(full_match.group(2)) if full_match.group(2) else None,
        }

        # Check if it matches our tilde (aka 'equal') exclusion syntax
        match = ott_details.match(result["node_name_in_parent"])
        base_ott = None
        if match:
            # split by minus signs
            result["excluded_otts"] = (match.group(3) or "").split("-")

            # If present, the first number after '=' is the tree to extract.
            first_number_after_equal = result["excluded_otts"].pop(0)
            base_ott = first_number_after_equal or match.group(2)

            # Note that we don't append the ott in the name if it came after the '='
            result["node_name_in_parent"] = match.group(1)
            if not first_number_after_equal:
                result["node_name_in_parent"] += f"_ott{base_ott}"

        # Check if OZ token has a base ott (e.g. 123 in foobar_ott123~456-789)
        if base_ott is not None:
            # It's an extracted Open Tree file, e.g. 123.phy
            # NB: We can't make a valid path without ot_parts_folder, but we probably don't care in this case
            result["base_ott"] = base_ott
            result["file"] = os.path.join(ot_parts_folder or ".", f"{base_ott}.phy")
            if ot_parts_folder and not os.path.exists(result["file"]):
                # Fall back to .nwk, which happens for additional copied files
                result["file"] = os.path.join(ot_parts_folder or ".", f"{base_ott}.nwk")
            result["override_edge_length"] = None
            result["override_taxon"] = None
            result["expand_nodes"] = False
        else:
            # Otherwise, it's a OneZoom file, e.g. AMORPHEA@ --> Amorphea.PHY
            child_mapping_entry = token_to_file_map[result["node_name_in_parent"]]
            result["base_ott"] = None
            result["file"] = os.path.join(oz_parts_folder or ".", child_mapping_entry["file"])
            result["override_edge_length"] = child_mapping_entry.get("edge_length", None)
            result["override_taxon"] = child_mapping_entry.get("taxon", None)
            result["expand_nodes"] = True

        logging.debug(result)
        yield result
