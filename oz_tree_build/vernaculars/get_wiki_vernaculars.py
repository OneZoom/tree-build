"""
This utility retrieves vernacular names from Wikidata for a given set of taxa or
tips in a clade. Either install the entire oz_tree_build package using
`python -m pip install oz_tree_build` or call the script directly as
`python -m oz_tree_build.vernaculars.get_wiki_vernaculars ...`.

The script can be used in two ways:
- To process a single taxon, use the 'leaf' subcommand. This will get the
  vernaculars for the given taxon, specified by OTT (e.g. 563151) or scientific
  name ('name') in the ordered_leaves or ordered_nodes tables e.g.
    * get_wiki_vernaculars.py leaf 563151
    * get_wiki_vernaculars.py leaf "Panthera leo"

- To process a full clade, use the 'clade' subcommand. This will get the
  vernaculars for all the taxa in the clade. A wikidata JSON dump file is
  required: ideally this should be a filtered one such as OneZoom_latest-all.json.
  For example, to get vernaculars for all Panthera:
    * get_wiki_vernaculars.py clade OneZoom_latest-all.json 563151   # or
    * get_wiki_vernaculars.py clade OneZoom_latest-all.json "Panthera"
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
    default_appconfig,
    placeholder,
    read_config,
    resolve_clade_bounds,
)
from ..utilities.wikidata_utils import (
    enumerate_wiki_dump_items,
    get_wikidata_json_for_qid,
    resolve_leaf,
)

logger = logging.getLogger(Path(__file__).name)


def get_vernaculars_by_language_from_json_item(json_item):
    """
    Get the vernacular names from a Wikidata JSON item for all languages.
    """

    vernaculars_by_language = {}
    known_canonical_vernaculars = set()

    # P1843 is the property for vernacular names
    try:
        for claim in json_item["claims"]["P1843"]:
            language = claim["mainsnak"]["datavalue"]["value"]["language"]

            vernacular_info = {
                "name": claim["mainsnak"]["datavalue"]["value"]["text"],
                "preferred": 1 if claim["rank"] == "preferred" else 0,
            }

            # Often multiple vernaculars exist that only differ in case or punctuation.
            # We only want to keep one of each for a given language.
            canonical_vernacular = language + "," + "".join(filter(str.isalnum, vernacular_info["name"])).lower()
            if canonical_vernacular in known_canonical_vernaculars:
                continue
            known_canonical_vernaculars.add(canonical_vernacular)

            vernaculars_by_language.setdefault(language, []).append(vernacular_info)
    except (KeyError, IndexError):
        return vernaculars_by_language

    # For each language:
    # - We keep all the vernaculars
    # - If none are marked as preferred, use the first non-preferred as preferred
    # - If multiple are marked as preferred, the first one will be kept as preferred
    for vernaculars in vernaculars_by_language.values():
        vernaculars.sort(reverse=True, key=lambda v: v["preferred"])
        for i, v in enumerate(vernaculars):
            v["preferred"] = 1 if i == 0 else 0
    return vernaculars_by_language


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


def process_leaf(db, ott_or_taxon, taxa_data=None):
    """
    If ott_or_taxon is a number it's an ott, otherwise it's a taxon name.
    """
    resolved = resolve_leaf(db, ott_or_taxon, taxa_data, logger)
    if resolved is None:
        return
    ott, qid, _name = resolved

    json_item = get_wikidata_json_for_qid(qid)
    vernaculars_by_language = get_vernaculars_by_language_from_json_item(json_item)
    save_wiki_vernaculars_for_qid(db, ott, qid, vernaculars_by_language)


def process_clade(db, ott_or_taxon, dump_file, taxa_data):
    s = placeholder(db)
    bounds = resolve_clade_bounds(db, ott_or_taxon, logger)
    if bounds is None:
        return
    (leaf_lft, leaf_rgt, _ott) = bounds

    # Get leaves in the clade with no wiki vernaculars, ignoring verns from other sources
    sql = f"""
    SELECT wikidata, ordered_leaves.ott FROM ordered_leaves
    LEFT OUTER JOIN (SELECT ott,src,vernacular FROM vernacular_by_ott WHERE src={s})
    as wiki_vernacular_by_ott ON ordered_leaves.ott=wiki_vernacular_by_ott.ott
    WHERE vernacular IS NULL AND ordered_leaves.id >= {s} AND ordered_leaves.id <= {s};
    """
    leaves_without_vn = dict(db.executesql(sql, (src_flags["wiki"], leaf_lft, leaf_rgt)))
    total_to_process = len(leaves_without_vn)
    logger.info(f"Found {total_to_process} taxa without a vernacular in the database")

    saved_count = 0
    start_time = time.time()
    for qid, vernaculars in enumerate_wiki_dump_items(dump_file, get_vernaculars_by_language_from_json_item):
        if vernaculars and qid in leaves_without_vn:
            save_wiki_vernaculars_for_qid(db, leaves_without_vn[qid], qid, vernaculars)
            saved_count += 1
            elapsed = time.time() - start_time
            logger.info(
                f"Saved vernaculars for ott={leaves_without_vn[qid]} (qid={qid}): "
                f"{saved_count} of {total_to_process} ({elapsed:.1f}s)"
            )

    logger.info(f"Finished: saved vernaculars for {saved_count} of {total_to_process} taxa")


def process_args(args):
    config = read_config(args.conf_file)
    database = config.get("db", "uri")
    db = connect_to_database(database)

    taxa_data = {}
    if args.taxa_data_file:
        with open(args.taxa_data_file) as f:
            taxa_data = json.load(f)

    if args.subcommand == "leaf":
        for name in args.ott_or_taxa:
            process_leaf(db, name, taxa_data)
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
        default=None,
        help=(f"The configuration file to use. Defaults to {default_appconfig}"),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])

    subparsers = parser.add_subparsers(help="help for subcommand", dest="subcommand")

    parser_leaf = subparsers.add_parser("leaf", help="Process a single ott")
    parser_leaf.add_argument("ott_or_taxa", nargs="+", type=str, help="The leaf otts or taxa to process")
    add_vernacular_common_args(parser_leaf)

    parser_clade = subparsers.add_parser("clade", help="Process a full clade")
    parser_clade.add_argument(
        "wd_dump",
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
