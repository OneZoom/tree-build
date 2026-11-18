"""
This utility retrieves vernacular names from Wikidata for a given set of taxa or
tips in a clade. Either install the entire oz_tree_build package using
`python -m pip install oz_tree_build` or call the script directly as
`python -m oz_tree_build.vernaculars.get_wiki_vernaculars ...`.
`--conf-file` (an appconfig.ini) is required.

The script can be used in two ways:
- To process a single taxon, use the 'taxon' subcommand. This will get the
  vernaculars for the given taxon, specified by OTT (e.g. 563151) or scientific
  name ('name') in the ordered_leaves or ordered_nodes tables e.g.
    * get_wiki_vernaculars.py taxon 563151
    * get_wiki_vernaculars.py taxon "Panthera leo"
    * get_wiki_vernaculars taxon 1028828 --conf-file /path/to/appconfig.ini
      (Strigidae, an internal node)
  This uses the Wikidata API and does not require a Wikidata dump.
  The previous 'leaf' subcommand remains available as an alias.

- To process a full clade, use the 'clade' subcommand. This will get the
  vernaculars for leaves and internal nodes in the clade that have OTTs.
  A wikidata JSON dump file is
  required: ideally this should be a filtered one such as OneZoom_latest-all.json.
  For example, to get vernaculars for all Panthera:
    * get_wiki_vernaculars.py clade 563151 --wd-dump OneZoom_latest-all.json   # or
    * get_wiki_vernaculars.py clade "Panthera" --wd-dump OneZoom_latest-all.json

Names come from P1843 statements and Wikidata labels. Preferred P1843 values
take priority, followed by a P1843 value matching the label, then the label,
then other P1843 values. Deprecated statements are ignored. Labels matching
P225 scientific names and labels in the special 'mul' language are excluded;
other labels may still be scientific names or transliterations.
"""

import argparse
import datetime
import json
import logging
import sys
import time
from pathlib import Path

from .._OZglobals import src_flags
from ..utilities.cli_utils import add_common_args, setup_logging
from ..utilities.db_helper import (
    connect_to_database,
    placeholder,
    read_config,
)
from ..utilities.wikidata_utils import (
    enumerate_wiki_dump_items,
    get_qid_from_taxa_data,
    get_wikidata_json_for_qid,
    validate_wikidata_dump,
)
from ..utilities.wikimedia_headers import wikimedia_headers

logger = logging.getLogger(Path(__file__).name)


def get_vernaculars_by_language_from_json_item(json_item):
    """
    Get P1843 names and eligible labels, preferring one name per language.
    """

    def canonical(name):
        return "".join(filter(str.isalnum, name)).casefold()

    claims = json_item.get("claims", {})
    scientific_names = {
        canonical(value)
        for claim in claims.get("P225", [])
        if isinstance(value := claim.get("mainsnak", {}).get("datavalue", {}).get("value"), str)
    }
    labels = {}
    for language, label in json_item.get("labels", {}).items():
        name = label.get("value")
        if isinstance(name, str) and canonical(name) and language.casefold() != "mul":
            if canonical(name) not in scientific_names:
                labels[language.casefold()] = name

    candidates = {}
    for claim in claims.get("P1843", []):
        if claim.get("rank") not in ("normal", "preferred"):
            continue
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        language, name = value.get("language"), value.get("text")
        if not isinstance(language, str) or not isinstance(name, str) or not language or not canonical(name):
            continue
        language = language.casefold()
        label = labels.get(language)
        priority = 0 if claim["rank"] == "preferred" else 1 if label and canonical(label) == canonical(name) else 3
        candidates.setdefault(language, []).append((priority, name))

    for language, name in labels.items():
        candidates.setdefault(language, []).append((2, name))

    result = {}
    for language, names in candidates.items():
        names.sort(key=lambda item: (item[0], canonical(item[1]), item[1]))
        seen = set()
        result[language] = []
        for _, name in names:
            key = canonical(name)
            if key not in seen:
                result[language].append({"name": name, "preferred": int(not seen)})
                seen.add(key)
    return result


def save_wiki_vernaculars_for_qid(db, ott, qid, vernaculars_by_language):
    """
    Save all vernacular names for a given QID to the database. Note that there
    can be multiple vernaculars for one language (e.g. "Lion" and "Africa Lion")
    """
    s = placeholder(db)
    # Delete any existing wiki vernaculars for this taxon from the database
    sql = f"DELETE FROM vernacular_by_ott WHERE ott={s} and src={s};"
    db.executesql(sql, (ott, src_flags["wiki"]))

    for language, vernaculars in vernaculars_by_language.items():
        # The wikidata language could either be a full language code (e.g. "en-us")
        # or just the primary code (e.g. "en"): make lang_primary just the primary code
        lang_primary = language.split("-")[0]

        for vernacular in vernaculars:
            # Only flag the first preferred vernacular for this source as preferred
            logger.info(
                f"Setting '{language}' vernacular for ott={ott} (qid={qid}, "
                f"preferred={vernacular['preferred']}): {vernacular['name']}"
            )

            # Insert the new vernacular into the database
            sql = (
                "INSERT INTO vernacular_by_ott "
                "(ott, vernacular, lang_primary, lang_full, preferred, src, src_id, "
                f"updated) VALUES ({s},{s},{s},{s},{s},{s},{s},{s});"
            )
            db._adapter.execute(  # alternative to executesql that doesn't commit
                sql,
                (
                    ott,
                    vernacular["name"],
                    lang_primary,
                    language,
                    vernacular["preferred"],
                    src_flags["wiki"],
                    qid,
                    datetime.datetime.now().isoformat(),
                ),
            )

    db.commit()


def process_taxon(db, ott_or_taxon, taxa_data=None):
    """Harvest vernaculars for one leaf or internal node."""
    column = "ott" if ott_or_taxon.lstrip("-").isnumeric() else "name"
    s = placeholder(db)
    rows = db.executesql(
        f"SELECT ott,wikidata,name FROM ordered_leaves WHERE {column}={s} "
        f"UNION ALL SELECT ott,wikidata,name FROM ordered_nodes WHERE {column}={s}",
        (ott_or_taxon, ott_or_taxon),
    )
    if not rows:
        logger.error(f"'{ott_or_taxon}' not found in ordered_leaves or ordered_nodes")
        return
    if len(rows) > 1:
        logger.error(f"Multiple results for '{ott_or_taxon}' in ordered_leaves and ordered_nodes")
        return
    ott, qid, name = rows[0]
    if ott is None:
        logger.error(f"'{ott_or_taxon}' has no OTT")
        return
    if not qid:
        qid = get_qid_from_taxa_data(taxa_data, name)
    if not qid:
        logger.error(f"No Wikidata QID for '{ott_or_taxon}'")
        return

    json_item = get_wikidata_json_for_qid(qid, headers=wikimedia_headers(auth=None))
    vernaculars_by_language = get_vernaculars_by_language_from_json_item(json_item)
    save_wiki_vernaculars_for_qid(db, ott, qid, vernaculars_by_language)


process_leaf = process_taxon


def process_clade(db, ott_or_taxon, dump_file, taxa_data):
    s = placeholder(db)
    column = "ott" if ott_or_taxon.lstrip("-").isnumeric() else "name"
    bounds = db.executesql(
        f"SELECT id,node_rgt,leaf_lft,leaf_rgt FROM ordered_nodes WHERE {column}={s}",
        (ott_or_taxon,),
    )
    if not bounds:
        raise ValueError(f"'{ott_or_taxon}' not found in ordered_nodes table")
    if len(bounds) > 1:
        logger.error(f"Multiple results for '{ott_or_taxon}' in ordered_nodes")
        return
    node_lft, node_rgt, leaf_lft, leaf_rgt = bounds[0]

    taxa_by_qid = {}
    for table, left, right in (
        ("ordered_leaves", leaf_lft, leaf_rgt),
        ("ordered_nodes", node_lft, node_rgt),
    ):
        sql = f"""
        SELECT taxon.wikidata, taxon.ott FROM {table} AS taxon
        WHERE taxon.id >= {s} AND taxon.id <= {s}
          AND taxon.ott IS NOT NULL AND taxon.wikidata IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM vernacular_by_ott AS vn WHERE vn.ott=taxon.ott AND vn.src={s}
          )
        """
        for qid, ott in db.executesql(sql, (left, right, src_flags["wiki"])):
            taxa_by_qid.setdefault(qid, set()).add(ott)
    total_to_process = sum(len(otts) for otts in taxa_by_qid.values())
    logger.info(f"Found {total_to_process} taxa without a vernacular in the database")

    saved_count = 0
    start_time = time.time()
    for qid, vernaculars in enumerate_wiki_dump_items(dump_file, get_vernaculars_by_language_from_json_item):
        if vernaculars and qid in taxa_by_qid:
            for ott in taxa_by_qid.pop(qid):
                save_wiki_vernaculars_for_qid(db, ott, qid, vernaculars)
                saved_count += 1
                elapsed = time.time() - start_time
                logger.info(
                    f"Saved vernaculars for ott={ott} (qid={qid}): "
                    f"{saved_count} of {total_to_process} ({elapsed:.1f}s)"
                )

    logger.info(f"Finished: saved vernaculars for {saved_count} of {total_to_process} taxa")


def process_args(args):
    if args.subcommand == "clade":
        validate_wikidata_dump(args.wd_dump)
    config = read_config(args.conf_file)
    database = config.get("db", "uri")
    db = connect_to_database(database)

    taxa_data = {}
    if args.taxa_data_file:
        with open(args.taxa_data_file) as f:
            taxa_data = json.load(f)

    if args.subcommand in ("taxon", "leaf"):
        for name in args.ott_or_taxa:
            process_taxon(db, name, taxa_data)
    elif args.subcommand == "clade":
        for name in args.ott_or_taxa:
            process_clade(db, name, args.wd_dump, taxa_data)


def add_vernacular_common_args(parser):
    add_common_args(parser)
    parser.add_argument(
        "--taxa-data-file",
        default=None,
        help="JSON file with persisted data about various taxa",
    )
    parser.add_argument(
        "-c",
        "--conf-file",
        required=True,
        help="Path to the appconfig.ini file to use",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])

    subparsers = parser.add_subparsers(help="help for subcommand", dest="subcommand")

    parser_taxon = subparsers.add_parser("taxon", aliases=["leaf"], help="Process individual taxa")
    parser_taxon.add_argument("ott_or_taxa", nargs="+", type=str, help="The OTTs or names to process")
    add_vernacular_common_args(parser_taxon)

    parser_clade = subparsers.add_parser("clade", help="Process a full clade")
    parser_clade.add_argument(
        "--wd-dump",
        required=True,
        type=str,
        help="The wikidata JSON dump file from which to get vernaculars",
    )
    parser_clade.add_argument(
        "ott_or_taxa",
        nargs="+",
        type=str,
        help="The ott or taxa of the root of the clade(s)",
    )
    add_vernacular_common_args(parser_clade)

    args = parser.parse_args()
    if not args.subcommand:
        parser.print_help()
        sys.exit()

    setup_logging(args)
    process_args(args)


if __name__ == "__main__":
    main()
