__author__ = "David Ebbo"

import logging
import re

'''
Enumerates all the OneZoom tokens in a tree string (e.g. foobar_ott123~-789-111)
'''
full_ott_token = re.compile(r"'?([\w\-~]+)@'?(?::([\d\.]+))?")
ott_details = re.compile(r"(\w+)_ott(\d*)~?([-\d]*)$")
def enumerate_one_zoom_tokens(tree):
    # Skip the comment block at the start of the file
    start_index = tree.index(']') if '[' in tree else 0

    for full_match in full_ott_token.finditer(tree, start_index):
        result = {'start': full_match.start(), 'end': full_match.end(),
                  'full_name': full_match.group(1),
                  'edge_length': float(full_match.group(2)) if full_match.group(2) else None}

        # Check if it matches our tilde (aka 'equal') exclusion syntax
        match = ott_details.match(result['full_name'])
        if match:
            result['excluded_otts'] = (match.group(3) or '').split('-') #split by minus signs

            # If present, the first number after '=' is the tree to extract.
            first_number_after_equal = result['excluded_otts'].pop(0)
            result['base_ott'] = first_number_after_equal or match.group(2) 

            # Note that we don't append the ott in the name if it came after the '='
            result['full_name'] = match.group(1)
            if not first_number_after_equal:
                result['full_name'] += f"_ott{result['base_ott']}"

        logging.debug(result)
        yield result
