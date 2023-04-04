"""
This code can be used in two different ways:
1. Filter the input files to remove many irrelevant things in order to make them smaller.
2. Generate test files that are a filtered subset of the full files, targeted at a specific clade/taxon.
"""

import argparse
import csv
import json
import logging
import os
import sys
import time

from oz_tree_build.newick.extract_trees import get_taxon_subtree_from_newick_file
from oz_tree_build.newick.newick_parser import parse_tree
from .temp_helpers import *
from .file_utils import *

__author__ = "David Ebbo"


def generate_and_cache_filtered_file(
    original_file, context, processing_function, bz2=False
):
    """
    Helper to perform caching of filtered files.
    """

    dir = os.path.dirname(original_file)
    file_name = os.path.basename(original_file)

    one_zoom_file_prefix = "OneZoom"
    filtered_file_prefix = (context.clade or one_zoom_file_prefix) + "_"
    if file_name.startswith(filtered_file_prefix):
        raise Exception(
            f"Input and output files are the same, with prefix {filtered_file_prefix}"
        )

    # If the original file is a OneZoom file, remove the OneZoom prefix to avoid double prefixes
    if file_name.startswith(one_zoom_file_prefix):
        file_name = file_name[len(one_zoom_file_prefix) + 1 :]

    # Include the clade in the new file name, e.g. '/foo/bar.csv.gz' --> '/foo/Mammalia_bar.csv.gz'
    # If no clade is specified, use 'OneZoom' instead as the prefix
    clade_filtered_file = os.path.join(dir, f"{filtered_file_prefix}{file_name}")

    if bz2 and not clade_filtered_file.endswith(".bz2"):
        clade_filtered_file += ".bz2"

    # Unless force is set, check if we already have a filtered file with the matching timestamp
    if not context.force:
        if os.path.exists(clade_filtered_file) and os.path.getmtime(
            clade_filtered_file
        ) == os.path.getmtime(original_file):
            logging.info(f"Using cached file {clade_filtered_file}")
            return clade_filtered_file

    logging.info(f"Generating file {clade_filtered_file}")

    # Call the processing function to generate the filtered file
    processing_function(original_file, clade_filtered_file, context)

    # Set the timestamp of the filtered file to match the original file
    os.utime(
        clade_filtered_file,
        (os.path.getatime(original_file), os.path.getmtime(original_file)),
    )

    logging.info(f"Finished generating file {clade_filtered_file}")

    return clade_filtered_file


def generate_filtered_newick(newick_file, filtered_newick_file, context):
    tree_string = get_taxon_subtree_from_newick_file(newick_file, context.clade)

    with open_file_based_on_extension(filtered_newick_file, "wt") as f:
        f.write(tree_string)


def read_newick_file(newick_file, context):
    with open_file_based_on_extension(newick_file, "rt") as f:
        filtered_tree_string = f.read()

    # Get the set of OTT ids from the filtered tree
    context.otts = {node["ott"] for node in parse_tree(filtered_tree_string)}


def generate_filtered_taxonomy_file(taxonomy_file, filtered_taxonomy_file, context):
    with open_file_based_on_extension(
        filtered_taxonomy_file, "wt"
    ) as filtered_taxonomy:
        for i, line in enumerate_lines_from_file(taxonomy_file):
            # Always copy the header
            if i == 0:
                filtered_taxonomy.write(line)
                continue

            # The ott id is the first column (known as the "uid" in the tsv file)
            fields = line.split("\t")
            ott = fields[0]

            # Only include lines that have an ott id in the filtered tree
            if ott in context.otts:
                filtered_taxonomy.write(line)


def read_taxonomy_file(taxonomy_file, context):
    sources = {"ncbi", "if", "worms", "irmng", "gbif"}
    context.source_ids = {source: set() for source in sources}

    # Get the sets of source ids we're actually using from the taxonomy file
    with open_file_based_on_extension(taxonomy_file, "rt") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for OTTrow in reader:
            sourceinfo = OTTrow["sourceinfo"]
            for srcs in sourceinfo.split(","):
                src, id = srcs.split(":", 1)
                if src in sources:
                    try:
                        context.source_ids[src].add(int(id))
                    except ValueError:
                        # Ignore it if it's not an integer
                        pass


def generate_filtered_eol_id_file(eol_id_file, filtered_eol_id_file, context):
    eol_sources = {"676": "ncbi", "459": "worms", "767": "gbif"}
    with open_file_based_on_extension(eol_id_file, "rt") as eol_f:
        with open_file_based_on_extension(filtered_eol_id_file, "wt") as filtered_eol_f:
            for i, line in enumerate(eol_f):
                # Always copy the header
                if i == 0:
                    filtered_eol_f.write(line)
                    continue

                fields = line.split(",")

                # Ignore it if it's not one of the known sources
                if not fields[2] in eol_sources:
                    continue

                try:
                    id = int(fields[1])
                except ValueError:
                    continue
                # Only include it if we saw that id in the taxonomy file
                if id in context.source_ids[eol_sources[fields[2]]]:
                    filtered_eol_f.write(line)

    logging.info(
        f"Found {len(context.source_ids['ncbi'])} NCBI ids, {len(context.source_ids['if'])} IF ids, {len(context.source_ids['worms'])} WoRMS ids, {len(context.source_ids['irmng'])} IRMNG ids, {len(context.source_ids['gbif'])} GBIF ids"
    )


def generate_filtered_wikidata_dump(
    wikipedia_dump_file, filtered_wikipedia_dump_file, context
):
    known_claims = {
        "P31",
        "P685",
        "P846",
        "P850",
        "P1391",
        "P5055",
        "P830",
        "P141",
        "P627",
        "P961",
    }
    included_qids = set()

    # We want all the vernacular lines to end up at the end of the file, so we
    # store them in a list. There are only a few hundred, so memory isn't
    # an issue.
    vernacular_json_items = []

    sitelinks_key = f"{context.wikilang}wiki"

    with open_file_based_on_extension(
        filtered_wikipedia_dump_file, "wt"
    ) as filtered_wiki_f:
        filtered_wiki_f.write("[\n")
        preserved_lines = 0

        for line_num, line in enumerate_lines_from_file(wikipedia_dump_file):
            if line_num > 0 and line_num % 100000 == 0:
                logging.info(
                    f"Kept {preserved_lines} out of {line_num} processed lines ({preserved_lines / line_num * 100:.2f}%))"
                )

            if not (line.startswith('{"type":') and quick_byte_match.search(line)):
                continue

            json_item = json.loads(line.rstrip().rstrip(","))

            try:
                is_taxon, vernaculars_matches = find_taxon_and_vernaculars(json_item)
            except KeyError:
                continue

            # If it's neither, ignore it
            if not is_taxon and not len(vernaculars_matches) > 0:
                continue

            # If it's a taxon but it doesn't map to any of our source ids, ignore it
            # We only do this if we're filtering by clade. When processing the full
            # tree, we want to keep all the taxa, even if they don't map to anything
            if (
                context.clade
                and is_taxon
                and not len(JSON_contains_known_dbID(json_item, context.source_ids)) > 0
            ):
                continue

            # Remove things we don't need at all
            if "descriptions" in json_item:
                del json_item["descriptions"]
            if "aliases" in json_item:
                del json_item["aliases"]

            # Only keep the English labels
            if context.wikilang in json_item["labels"]:
                json_item["labels"] = {
                    "language": json_item["labels"][context.wikilang]
                }
            else:
                json_item["labels"] = {}

            # Only keep the claims we care about
            json_item["claims"] = {
                k: v for k, v in json_item["claims"].items() if k in known_claims
            }

            # Only keep the sitelinks that end in "wiki", e.g. enwiki, dewiki, etc.
            # And among those, only keep the original value for the language we want, since the
            # rest is just needed to collect the language names into the bit field
            json_item["sitelinks"] = {
                k: v if k == sitelinks_key else {}
                for k, v in json_item["sitelinks"].items()
                if k.endswith("wiki")
            }

            if is_taxon:
                # Write out the line. We set the separators to avoid spaces
                filtered_wiki_f.write(json.dumps(json_item, separators=(",", ":")))
                filtered_wiki_f.write(",\n")

                included_qids.add(Qid(json_item))

                preserved_lines += 1
            else:
                # If it's vernacular, we'll write it out at the end, so save it
                vernacular_json_items.append((vernaculars_matches, json_item))

        # Write out the relevant vernacular lines at the end
        logging.info(f"Writing vernacular lines at the end of the file")
        for vernaculars_matches, json_item in vernacular_json_items:
            for qid in vernaculars_matches:
                if qid in included_qids:
                    filtered_wiki_f.write(json.dumps(json_item, separators=(",", ":")))
                    filtered_wiki_f.write(",\n")
                    logging.info(
                        f"Including vernacular entry '{get_label(json_item)}' ({get_wikipedia_name(json_item)}), mapped to Q={qid}"
                    )
                    break

        filtered_wiki_f.write("]\n")


def read_wikidata_dump(wikidata_dump_file, context):
    context.wikidata_ids = set()

    for line_num, line in enumerate_lines_from_file(wikidata_dump_file):
        if not line.startswith('{"type":'):
            continue

        json_item = json.loads(line.rstrip().rstrip(","))
        context.wikidata_ids.add(get_wikipedia_name(json_item))


def generate_filtered_wikipedia_sql_dump(
    wikipedia_sql_dump_file, filtered_wikipedia_sql_dump_file, context
):
    # the column numbers for each datum are specified in the SQL file, and hardcoded here.
    page_table_namespace_column = 2
    page_table_title_column = 3
    page_table_pagelen_column = 10

    with open_file_based_on_extension(
        filtered_wikipedia_sql_dump_file, "wt"
    ) as filtered_sql_f:
        current_output_line_entry_count = 0
        max_entries_per_line = 10
        with open_file_based_on_extension(wikipedia_sql_dump_file, "rt") as sql_f:
            pagelen_file = csv.reader(sql_f, quotechar="'", doublequote=True)
            match_line = "INSERT INTO `page` VALUES "
            for fields in filter(
                lambda x: False if len(x) == 0 else x[0].startswith(match_line),
                pagelen_file,
            ):
                field_num = 0
                # the records are all on the same line, separated by '),(', so we need to count fields into the line.
                for field in fields:
                    try:
                        if field.lstrip()[0] == "(":
                            field_num = 0
                            namespace = None
                            title = None
                    except IndexError:
                        pass
                    field_num += 1
                    if field_num == page_table_namespace_column:
                        namespace = field
                    if field_num == page_table_title_column:
                        title = field
                    elif field_num == page_table_pagelen_column and namespace == "0":
                        # Only include it if it's one of our wikidata ids
                        if title in context.wikidata_ids:
                            if current_output_line_entry_count == 0:
                                filtered_sql_f.write(match_line)
                            else:
                                filtered_sql_f.write(",")

                            # Escape the quotes in the title
                            title = title.replace("'", "''")

                            # We leave all the other fields empty, as we don't need them
                            # e.g. (,0,'Pan_paniscus',,,,,,,87,,)
                            filtered_sql_f.write(
                                f"(,{namespace},'{title}',,,,,,,{field},,)"
                            )

                            current_output_line_entry_count += 1
                            if current_output_line_entry_count == max_entries_per_line:
                                filtered_sql_f.write(";\n")
                                current_output_line_entry_count = 0


def generate_filtered_pageviews_file(pageviews_file, filtered_pageviews_file, context):
    match_project = context.wikilang + ".z "

    with open_file_based_on_extension(filtered_pageviews_file, "wt") as filtered_bz2_f:
        for i, line in enumerate_lines_from_file(pageviews_file):
            if i > 0 and i % 10000000 == 0:
                logging.info(f"Processed {i} lines")
            if not line.startswith(match_project):
                continue

            info = line[len(match_project) :].rstrip("\n").rsplit(" ", 1)
            title = info[0].replace(
                " ", "_"
            )  # even though most titles should not have spaces, some can sneak in via uri escaping
            # Only include it if it's one of our wikidata ids
            if title in context.wikidata_ids:
                filtered_bz2_f.write(line)


def generate_all_filtered_files(
    context,
    newick_file,
    taxonomy_file,
    eol_id_file,
    wikidata_dump_file,
    wikipedia_sql_dump_file,
    wikipedia_pageviews_files,
):

    if context.clade:
        # If we're filtering by clade, we need to generate a filtered newick
        filtered_newick_file = generate_and_cache_filtered_file(
            newick_file, context, generate_filtered_newick
        )
        read_newick_file(filtered_newick_file, context)

        # We also need to generate a filtered taxonomy file
        filtered_taxonomy_file = generate_and_cache_filtered_file(
            taxonomy_file, context, generate_filtered_taxonomy_file
        )
    else:
        # If we're not filtering by clade, there is really nothing to filter,
        # so we just use the original taxonomy file directly.
        # Note that we completely ignore the newick file in this case.
        filtered_taxonomy_file = taxonomy_file
    read_taxonomy_file(filtered_taxonomy_file, context)

    generate_and_cache_filtered_file(
        eol_id_file, context, generate_filtered_eol_id_file
    )

    filtered_wikidata_dump_file = generate_and_cache_filtered_file(
        wikidata_dump_file, context, generate_filtered_wikidata_dump, bz2=True
    )
    # filtered_wikipedia_dump_file = generate_and_cache_filtered_file(wikidata_dump_file, context, generate_filtered_wikipedia_dump)
    read_wikidata_dump(filtered_wikidata_dump_file, context)

    generate_and_cache_filtered_file(
        wikipedia_sql_dump_file, context, generate_filtered_wikipedia_sql_dump
    )

    for wikipedia_pageviews_file in wikipedia_pageviews_files:
        generate_and_cache_filtered_file(
            wikipedia_pageviews_file, context, generate_filtered_pageviews_file
        )


def main():
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("Tree", help="The newick format tree to use")
    parser.add_argument(
        "OpenTreeTaxonomy",
        help="The 325.6 MB Open Tree of Life taxonomy.tsv file, from http://files.opentreeoflife.org/ott/",
    )
    parser.add_argument(
        "EOLidentifiers",
        help="The gzipped 450 MB EOL identifiers file, from https://opendata.eol.org/dataset/identifiers-csv-gz",
    )
    parser.add_argument(
        "wikidataDumpFile",
        nargs="?",
        help="The b2zipped >4GB wikidata JSON dump, from https://dumps.wikimedia.org/wikidatawiki/entities/ (latest-all.json.bz2) ",
    )
    parser.add_argument(
        "wikipediaSQLDumpFile",
        nargs="?",
        help="The gzipped >1GB wikipedia -latest-page.sql.gz dump, from https://dumps.wikimedia.org/enwiki/latest/ (enwiki-latest-page.sql.gz) ",
    )
    parser.add_argument(
        "wikipedia_totals_bz2_pageviews",
        nargs="*",
        help='One or more b2zipped "totals" pageview count files, from https://dumps.wikimedia.org/other/pagecounts-ez/merged/ (e.g. pagecounts-2016-01-views-ge-5-totals.bz2, or pagecounts*totals.bz2)',
    )
    parser.add_argument(
        "--clade", "-c", help="The clade for which to generate the files"
    )
    parser.add_argument(
        "--force",
        "-f",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="If true, forces the regeneration of all files, ignoring caching.",
    )
    args = parser.parse_args()

    # Create a context object to hold various things we need to pass around
    context = type(
        "", (object,), {"wikilang": "en", "clade": args.clade, "force": args.force}
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
    logging.debug("Time taken: {} seconds".format(end - start))


if __name__ == "__main__":
    main()
