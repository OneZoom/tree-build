"""
This code can be used in two different ways:
1. Filter the input files to remove many irrelevant things in order to make them smaller.
2. Generate test files that are a filtered subset of the full files,
   targeted at a specific clade/taxon.

For the DVC pipeline, the individual filter modules (filter_eol, filter_wikidata,
filter_wikipedia_sql, filter_pageviews) are run as separate stages. This module
provides the orchestrating function used for clade-specific test filtering.
"""

import argparse
import logging
import os
import sys
import time

from ..newick.extract_trees import get_taxon_subtree_from_newick_file
from ..newick.newick_parser import parse_tree
from .file_utils import enumerate_lines_from_file, open_file_based_on_extension
from .filter_common import read_taxonomy_source_ids
from .filter_eol import filter_eol_ids
from .filter_pageviews import filter_pageviews
from .filter_wikidata import extract_wikidata_titles, filter_wikidata
from .filter_wikipedia_sql import filter_wikipedia_sql

__author__ = "David Ebbo"

one_zoom_file_prefix = "OneZoom"


def _compute_output_path(original_file, prefix, compress=False):
    """Compute the output path for a filtered file given a prefix (clade or OneZoom)."""
    dirname = os.path.dirname(original_file)
    file_name = os.path.basename(original_file)

    if file_name.startswith(one_zoom_file_prefix):
        file_name = file_name[len(one_zoom_file_prefix) + 1 :]

    output_file = os.path.join(dirname, f"{prefix}_{file_name}")

    if not compress:
        if output_file.endswith(".gz") or output_file.endswith(".bz2"):
            output_file = os.path.splitext(output_file)[0]

    return output_file


def generate_filtered_newick(newick_file, filtered_newick_file, clade):
    tree_string = get_taxon_subtree_from_newick_file(newick_file, clade)
    with open_file_based_on_extension(filtered_newick_file, "wt") as f:
        f.write(tree_string)


def read_newick_otts(newick_file):
    with open_file_based_on_extension(newick_file, "rt") as f:
        tree_string = f.read()
    return {node["ott"] for node in parse_tree(tree_string)}


def generate_filtered_taxonomy_file(taxonomy_file, filtered_taxonomy_file, otts):
    with open_file_based_on_extension(filtered_taxonomy_file, "wt") as filtered_taxonomy:
        for i, line in enumerate_lines_from_file(taxonomy_file):
            if i == 0:
                filtered_taxonomy.write(line)
                continue

            fields = line.split("\t")
            ott = fields[0]

            if ott in otts:
                filtered_taxonomy.write(line)


def generate_all_filtered_files(
    context,
    newick_file,
    taxonomy_file,
    eol_id_file,
    wikidata_dump_file,
    wikipedia_sql_dump_file,
    wikipedia_pageviews_files,
):
    """
    Orchestrate all filtering steps. Used for clade-specific test filtering
    and as a convenience wrapper. For the DVC pipeline, the individual filter
    modules are invoked as separate stages instead.
    """
    prefix = context.clade or one_zoom_file_prefix

    if context.clade:
        filtered_newick_file = _compute_output_path(newick_file, prefix, context.compress)
        generate_filtered_newick(newick_file, filtered_newick_file, context.clade)
        otts = read_newick_otts(filtered_newick_file)

        filtered_taxonomy_file = _compute_output_path(taxonomy_file, prefix, context.compress)
        generate_filtered_taxonomy_file(taxonomy_file, filtered_taxonomy_file, otts)
    else:
        filtered_taxonomy_file = taxonomy_file

    source_ids = read_taxonomy_source_ids(filtered_taxonomy_file)

    if eol_id_file:
        eol_output = _compute_output_path(eol_id_file, prefix, context.compress)
        filter_eol_ids(eol_id_file, eol_output, source_ids, clade=context.clade)

    if wikidata_dump_file:
        wikidata_output = _compute_output_path(wikidata_dump_file, prefix, context.compress)
        lines = (line for _, line in enumerate_lines_from_file(wikidata_dump_file))
        filter_wikidata(
            lines,
            wikidata_output,
            source_ids=source_ids if context.clade else None,
            clade=context.clade,
            wikilang=context.wikilang,
            dont_trim_sitelinks=context.dont_trim_sitelinks,
        )
        wikidata_titles = extract_wikidata_titles(wikidata_output)
    else:
        wikidata_titles = set()

    if wikipedia_sql_dump_file:
        sql_output = _compute_output_path(wikipedia_sql_dump_file, prefix, context.compress)
        filter_wikipedia_sql(wikipedia_sql_dump_file, sql_output, wikidata_titles)

    if wikipedia_pageviews_files:
        for pv_file in wikipedia_pageviews_files:
            pv_output = _compute_output_path(pv_file, prefix, context.compress)
            filter_pageviews(pv_file, pv_output, wikidata_titles, wikilang=context.wikilang)


def process_args(args):
    context = type(
        "",
        (object,),
        {
            "wikilang": "en",
            "clade": args.clade,
            "compress": args.compress,
            "force": args.force,
            "dont_trim_sitelinks": args.dont_trim_sitelinks,
        },
    )()

    start = time.time()

    generate_all_filtered_files(
        context,
        args.Tree,
        args.OpenTreeTaxonomy,
        args.EOLidentifiers,
        args.wikidataDumpFile,
        args.wikipediaSQLDumpFile,
        args.wikipedia_totals_bz2_pageviews,
    )

    end = time.time()
    logging.debug(f"Time taken: {end - start} seconds")


def main():
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("Tree", help="The newick format tree to use")
    parser.add_argument(
        "OpenTreeTaxonomy",
        help="The OpenTree taxonomy.tsv file, from http://files.opentreeoflife.org/ott/",
    )
    parser.add_argument(
        "--EOLidentifiers",
        help="The gzipped EOL identifiers file (optional, previously from opendata.eol.org)",
    )
    parser.add_argument(
        "wikidataDumpFile",
        nargs="?",
        help=(
            "The b2zipped >4GB wikidata JSON dump, "
            "from https://dumps.wikimedia.org/wikidatawiki/entities/ (latest-all.json.bz2). "
            f"If this starts with '{one_zoom_file_prefix}', it is assumed to be filtered "
            "already, which is useful if the original dumpfile is missing and additional "
            "pageview files require filtering."
        ),
    )
    parser.add_argument(
        "wikipediaSQLDumpFile",
        nargs="?",
        help=(
            "The gzipped >1GB wikipedia -latest-page.sql.gz dump, "
            "from https://dumps.wikimedia.org/enwiki/latest/ (enwiki-latest-page.sql.gz) "
        ),
    )
    parser.add_argument(
        "wikipedia_totals_bz2_pageviews",
        nargs="*",
        help=(
            'One or more b2zipped "totals" pageview count files, '
            "from https://dumps.wikimedia.org/other/pagecounts-ez/merged/ "
            "(e.g. pagecounts-2016-01-views-ge-5-totals.bz2, or pagecounts*totals.bz2)"
        ),
    )
    parser.add_argument("--clade", "-c", help="The clade for which to generate the files")
    parser.add_argument(
        "--compress",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="If true, generate compressed file if the source is compressed",
    )
    parser.add_argument(
        "--force",
        "-f",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="If true, forces the regeneration of all files (ignored, kept for CLI compatibility).",
    )
    parser.add_argument(
        "--dont_trim_sitelinks",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="If true, keep the full sitelinks value for all languages",
    )
    args = parser.parse_args()

    process_args(args)


if __name__ == "__main__":
    main()
