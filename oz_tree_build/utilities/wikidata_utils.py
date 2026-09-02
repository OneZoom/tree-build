"""
Shared Wikidata helpers for the wiki image and vernacular harvesting scripts.
"""

import json

from .db_helper import placeholder
from .file_utils import enumerate_lines_from_file
from .http_utils import make_http_request_with_retries


def get_wikidata_json_for_qid(qid, headers):
    """
    Use the Wikidata API to get the JSON for a given QID. This is faster than
    using the dump file when we only need a single item. It's worth noting that this
    gets the latest version of the item, which may not be the same as the dump file.
    """
    wikidata_url = f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q{qid}&format=json"
    r = make_http_request_with_retries(wikidata_url, headers=headers)
    return r.json()["entities"][f"Q{qid}"]


def get_prop_from_taxa_data(taxa_data, taxon, prop):
    """
    Get a property for a taxon from the taxa data dictionary.
    """
    if taxa_data is None:
        return None
    if taxon in taxa_data:
        data = taxa_data[taxon]
        if not data:
            return None
        if "redirect" in data:
            data = taxa_data[data["redirect"]]
        if prop in data:
            return data[prop]
    return None


def get_qid_from_taxa_data(taxa_data, taxon):
    return get_prop_from_taxa_data(taxa_data, taxon, "qid")


def enumerate_wiki_dump_items(wikidata_dump_file, extract_item):
    """
    Enumerate the items in a Wikidata JSON dump, yielding (qid, extract_item(json_item))
    for each item.
    """
    for _, line in enumerate_lines_from_file(wikidata_dump_file):
        if not (line.startswith('{"type":')):
            continue
        json_item = json.loads(line.rstrip().rstrip(","))
        qid = int(json_item["id"][1:])
        yield qid, extract_item(json_item)


def resolve_leaf(db, ott_or_taxon, taxa_data, logger):
    """
    Find the ott, qid and name for a leaf, specified either by ott or by taxon
    name, by looking it up in the ordered_leaves table. If no qid is found in
    the database, fall back to the passed-in taxa_data. Returns None (after
    logging an error) if the leaf can't be resolved.
    """
    # Real otts are never negative, but we abuse them in our tests, so account for that.
    s = placeholder(db)
    sql = "SELECT ott,wikidata,name FROM ordered_leaves WHERE "
    if ott_or_taxon.lstrip("-").isnumeric():
        ott_or_taxon_type = "ott"
        sql += f"ott={s};"
    else:
        ott_or_taxon_type = "name"
        sql += f"name={s};"

    result = db.executesql(sql, (ott_or_taxon,))
    if len(result) > 1:
        logger.error(f"Multiple results for '{ott_or_taxon}'")
        return None
    if len(result) == 0:
        logger.error(f"{ott_or_taxon_type} '{ott_or_taxon}' not found in ordered_leaves table")
        return None

    (ott, qid, name) = result[0]
    logger.info(f"Processing '{name}' (ott={ott}, qid={qid})")

    # If we didn't get a qid from the database, try to get it from the taxa data
    if qid is None:
        qid = get_qid_from_taxa_data(taxa_data, name)

    return ott, qid, name
