'''
Helpers copied from OTT_popularity_mapping.py.
TODO: Should be moved to a shared location.
'''

import logging
import re


# See https://en.wikipedia.org/wiki/Module:Taxonbar#L-195 for the full list
match_taxa = {
    16521: 'taxon',
    310890: 'monotypic taxon',
    23038290: 'fossil taxon',
    713623: 'clade',
}
match_vernacular = {
    502895: 'common name',
    55983715: 'group of organisms known by one particular common name',
}

regexp_match = '|'.join([str(v) for v in list(match_taxa) + list(match_vernacular)])
quick_byte_match = re.compile('numeric-id":(?:{})\D'.format(regexp_match))

def wikidata_value(wd_json, err=False):
    """
    used to get the value dict out of a wd parsed object
    If err==False, do not error out (allows use in a list comprehension)
    """
    try:
        return wd_json["datavalue"]["value"]
    except (KeyError, TypeError):
        return {}


def get_label(json_item, lang='en'):
    try:
        return json_item['labels'][lang]['value']
    except LookupError:
        return("no name for lang = {}".format(lang))

def Qid(json_item):
    return int(json_item['id'].replace("Q","",1))

def JSON_contains_known_dbID(json_item, known_items):
    """
    Return a dict of the source types and ids for this json_item, (e.g.
    {'ncbi': 1234, 'gbif': 4567}, etc.
    """
    wikidata_db_props = {'P685':'ncbi','P846':'gbif','P850':'worms','P1391':'if', 'P5055': 'irmng'}
    ret = {}
    for taxon_id_prop, source in wikidata_db_props.items():
        if taxon_id_prop in json_item['claims']:
            claim = json_item['claims'][taxon_id_prop]
            if source in ret:
                logging.warning(
                    f"Multiple {source} IDs for Q{Qid(json_item)} ({get_label(json_item)}); "
                    "taking the last one"
                )
            try:
                src_id = wikidata_value(claim[0]['mainsnak'], err=True)
            except (KeyError, ValueError, TypeError):
                logging.warning(  # Lots of wikidata items may not be in 
                    f"Can't find a value for {source} for Q{Qid(json_item)} "
                    f"({get_label(json_item)}) in wikidata")
                continue
            if src_id:
                try:
                    if int(src_id) in known_items[source]:
                        ret[source] = int(src_id)
                except ValueError:
                    if src_id in known_items[source]:
                        ret[source] = src_id
    return ret

def find_taxon_and_vernaculars(json_item):
    is_taxon = False
    vernaculars = set()
    instance_of = json_item['claims']['P31']

    for i in instance_of:
        nid = wikidata_value(i.get("mainsnak")).get("numeric-id")

        if nid in match_taxa:
            is_taxon = True
        elif nid in match_vernacular:
            for alt in i.get("qualifiers", {}).get('P642', []):
                vernaculars.add(wikidata_value(alt).get("numeric-id"))

    return is_taxon, vernaculars

def get_wikipedia_name(json_item):
    try:
        return json_item['sitelinks']['enwiki']['title'].replace(" ", "_")
    except KeyError:
        return None
