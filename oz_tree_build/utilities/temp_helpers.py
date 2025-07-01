"""
Helpers copied from OTT_popularity_mapping.py.
TODO: Should be moved to a shared location.
"""

import re

from ..taxon_mapping_and_popularity.OTT_popularity_mapping import (
    match_synonym,
    match_taxa,
    match_vernacular,
    wikidata_value,
)

regexp_match = "|".join([str(v) for v in list(match_taxa) + list(match_vernacular)])
quick_byte_match = re.compile(f'numeric-id":(?:{regexp_match})\\D')


def find_taxon_and_vernaculars(json_item):
    is_taxon = False
    vernaculars = set()
    instance_of = json_item["claims"]["P31"]

    for i in instance_of:
        nid = wikidata_value(i.get("mainsnak")).get("numeric-id")

        if nid in match_taxa:
            is_taxon = True
        elif nid in match_vernacular or nid in match_synonym:
            for alt in i.get("qualifiers", {}).get("P642", []):
                vernaculars.add(wikidata_value(alt).get("numeric-id"))

    return is_taxon, vernaculars


def get_wikipedia_name(json_item):
    try:
        return json_item["sitelinks"]["enwiki"]["title"].replace(" ", "_")
    except KeyError:
        return None
