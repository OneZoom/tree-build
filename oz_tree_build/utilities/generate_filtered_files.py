"""
This code can be used in two different ways:
1. Filter the input files to remove many irrelevant things in order to make them smaller.
2. Generate test files that are a filtered subset of the full files,
   targeted at a specific clade/taxon.
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from collections import defaultdict

from oz_tree_build._OZglobals import wikiflags
from oz_tree_build.newick.extract_trees import get_taxon_subtree_from_newick_file
from oz_tree_build.newick.newick_parser import parse_tree
from oz_tree_build.taxon_mapping_and_popularity.CSV_base_table_creator import iucn_num
from oz_tree_build.taxon_mapping_and_popularity.OTT_popularity_mapping import (
    JSON_contains_known_dbID,
    Qid,
    label,
)

from .apply_mask_to_object_graph import ANY, KEEP, apply_mask_to_object_graph
from .file_utils import enumerate_lines_from_file, open_file_based_on_extension
from .temp_helpers import (
    find_taxon_and_vernaculars,
    get_wikipedia_name,
    quick_byte_match,
    wikidata_value,
)

__author__ = "David Ebbo"


def generate_and_cache_filtered_file(original_file, context, processing_function):
    """
    Helper to perform caching of filtered files.
    """

    dirname = os.path.dirname(original_file)
    file_name = os.path.basename(original_file)

    one_zoom_file_prefix = "OneZoom"
    filtered_file_prefix = (context.clade or one_zoom_file_prefix) + "_"
    if file_name.startswith(filtered_file_prefix):
        raise Exception(f"Input and output files are the same, with prefix {filtered_file_prefix}")

    # If original file is a OneZoom file, remove the OneZoom prefix to avoid double prefixes
    if file_name.startswith(one_zoom_file_prefix):
        file_name = file_name[len(one_zoom_file_prefix) + 1 :]

    # Include clade in new file name, e.g. '/foo/bar.csv.gz' --> '/foo/Mammalia_bar.csv.gz'
    # If no clade is specified, use 'OneZoom' instead as the prefix
    clade_filtered_file = os.path.join(dirname, f"{filtered_file_prefix}{file_name}")

    # If we're not compressing and it has a .gz or .bz2 extension, remove it
    if not context.compress:
        if clade_filtered_file.endswith(".gz") or clade_filtered_file.endswith(".bz2"):
            clade_filtered_file = os.path.splitext(clade_filtered_file)[0]

    # Unless force is set, check we already have a filtered file with the matching timestamp
    if not context.force:
        if os.path.exists(clade_filtered_file) and os.path.getmtime(clade_filtered_file) == os.path.getmtime(
            original_file
        ):
            logging.info(f"Using cached file {clade_filtered_file}")
            return clade_filtered_file

    # If the filtered file already exists, rename it to include the timestamp, so we don't overwrite it
    if os.path.exists(clade_filtered_file):
        existing_file_time = os.path.getmtime(clade_filtered_file)
        renamed_file_name = (
            os.path.splitext(clade_filtered_file)[0]
            + "_"
            + time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(existing_file_time))
            + os.path.splitext(clade_filtered_file)[1]
        )
        os.rename(clade_filtered_file, renamed_file_name)
        logging.info(f"Renamed existing file to {renamed_file_name}")

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
    with open_file_based_on_extension(filtered_taxonomy_file, "wt") as filtered_taxonomy:
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
                src, src_id = srcs.split(":", 1)
                if src in sources:
                    try:
                        context.source_ids[src].add(int(src_id))
                    except ValueError:
                        # Ignore it if it's not an integer
                        pass


def generate_filtered_eol_id_file(eol_id_file, filtered_eol_id_file, context):
    eol_sources = {"676": "ncbi", "459": "worms", "767": "gbif", str(iucn_num): "iucn"}
    iucn_lines = []
    known_names = set()

    with open_file_based_on_extension(eol_id_file, "rt") as eol_f:
        with open_file_based_on_extension(filtered_eol_id_file, "wt") as filtered_eol_f:
            for i, line in enumerate(eol_f):
                # Always copy the header
                if i == 0:
                    filtered_eol_f.write(line)
                    continue

                fields = line.split(",")

                # Ignore it if it's not one of the known sources
                if fields[2] not in eol_sources:
                    continue

                try:
                    eol_id = int(fields[1])
                except ValueError:
                    # Some lines have the eol_id set to a weird value, e.g.
                    # "Animalia/Arthropoda/Malacostraca/Cumacea/Pseudocumatidae/Strauchia"
                    # We ignore these
                    continue

                if not context.clade:
                    # If we're not filtering by clade, keep all the lines
                    filtered_eol_f.write(line)
                    continue

                # If it's an IUCN line, just save it for now
                if fields[2] == str(iucn_num):
                    iucn_lines.append(line)
                # For other providers, only include it if we saw it in the taxonomy file
                elif eol_id in context.source_ids[eol_sources[fields[2]]]:
                    filtered_eol_f.write(line)
                    known_names.add(fields[4])

            # Include any IUCN lines that have a name that we encountered
            for line in iucn_lines:
                fields = line.split(",")
                if fields[4] in known_names:
                    filtered_eol_f.write(line)

    logging.info(
        f"Found {len(context.source_ids['ncbi'])} NCBI ids, "
        f"{len(context.source_ids['if'])} IF ids, "
        f"{len(context.source_ids['worms'])} WoRMS ids, "
        f"{len(context.source_ids['irmng'])} IRMNG ids, "
        f"{len(context.source_ids['gbif'])} GBIF ids"
    )


def generate_filtered_wikidata_dump(wikipedia_dump_file, filtered_wikipedia_dump_file, context):
    # This mask defines which fields we want to keep from the wikidata dump
    # The goal is to keep it structurally the same as the original, but only
    # include the fields we actually consume
    mask = {
        "type": KEEP,  # Only needed for the quick 'startswith()' line check
        "id": KEEP,
        "labels": {"en": {"value": KEEP}},
        "claims": {
            "P31": [
                {
                    "mainsnak": {"datavalue": {"value": {"numeric-id": KEEP}}},
                    "qualifiers": {
                        "P642": [{"datavalue": {"value": {"numeric-id": KEEP}}}]
                    },  # "of" (applies within the scope of a particular item)
                }
            ],  # Instance of
            "P685": [{"mainsnak": {"datavalue": {"value": KEEP}}}],  # ncbi id
            "P846": [{"mainsnak": {"datavalue": {"value": KEEP}}}],  # gbif id
            "P850": [{"mainsnak": {"datavalue": {"value": KEEP}}}],  # worms id
            "P1391": [{"mainsnak": {"datavalue": {"value": KEEP}}}],  # if id
            "P5055": [{"mainsnak": {"datavalue": {"value": KEEP}}}],  # irmng id
            "P830": [{"mainsnak": {"datavalue": {"value": KEEP}}}],  # EOL id
            "P961": [{"mainsnak": {"datavalue": {"value": KEEP}}}],  # IPNI id
            "P9157": [{"mainsnak": {"datavalue": {"value": KEEP}}}],  # OTT id
            "P3151": [{"mainsnak": {"datavalue": {"value": KEEP}}}],  # iNaturalist id
            "P141": [{"references": [{"snaks": {"P627": [{"datavalue": {"value": KEEP}}]}}]}],  # IUCN id
            "P1420": [{"mainsnak": {"datavalue": {"value": {"numeric-id": KEEP}}}}],  # taxon synonym
            "P18": [
                {
                    "mainsnak": {"datavalue": {"value": KEEP}},
                    "rank": KEEP,
                }
            ],  # image
            "P1843": [
                {
                    "mainsnak": {"datavalue": {"value": KEEP}},
                    "rank": KEEP,
                }
            ],  # taxon common name (aka vernaculars)
        },
        "sitelinks": {ANY: {"title": KEEP}},
    }

    sitelinks_key = f"{context.wikilang}wiki"

    def trim_and_write_json_item(json_item, filtered_wiki_f):
        # Remove everything we don't need from the json
        apply_mask_to_object_graph(json_item, mask)

        # Only keep the sitelinks that end in "wiki", e.g. enwiki, dewiki, etc.
        # (leave out those ending in "wikiquote", "wikivoyage", "wikinews", "wikibooks", etc.)
        if context.dont_trim_sitelinks:
            # Keep the full sitelinks value for all languages if flag is passed
            json_item["sitelinks"] = {k: v for k, v in json_item["sitelinks"].items() if k.endswith("wiki")}
        else:
            # Otherwise only keep the original value for the language we want, since the
            # rest is just needed to collect the language names into the bit field
            # Also, limit the sitelinks to the languages we care about for the bit field
            json_item["sitelinks"] = {
                k: v if k == sitelinks_key else {}
                for k, v in json_item["sitelinks"].items()
                if k.endswith("wiki") and len(k) == 6 and k[:2] in wikiflags
            }

        # Write out a line. We set the separators to avoid spaces
        filtered_wiki_f.write(json.dumps(json_item, separators=(",", ":")))
        filtered_wiki_f.write(",\n")

    included_qids = set()

    # Keep track of vernaculars and taxon synonyms that we might want to include at the end
    # There are only a few hundred, so memory isn't an issue.
    potential_extra_json_items = []

    with open_file_based_on_extension(filtered_wikipedia_dump_file, "wt") as filtered_wiki_f:
        filtered_wiki_f.write("[\n")
        preserved_lines = 0

        def get_line_message(line_num):
            return f"Kept {preserved_lines}/{line_num} lines ({preserved_lines / line_num * 100:.2f}%)"

        for _, line in enumerate_lines_from_file(wikipedia_dump_file, 100000, get_line_message):
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

            # When clade filter, we only want to keep the taxa that map to source ids.
            # In addition, when it doesn't map to any, we want to track it if it's
            # a synonym, so we may end up including it at the end.
            if context.clade and is_taxon:
                if not len(JSON_contains_known_dbID(json_item, context.source_ids)) > 0:
                    # Case 1: it could have taxon synonyms via P1420
                    if "P1420" in json_item["claims"] and json_item["sitelinks"]:
                        potential_extra_json_items.append(
                            (
                                "taxon_synonym",
                                {wikidata_value(i["mainsnak"])["numeric-id"] for i in json_item["claims"]["P1420"]},
                                json_item,
                            )
                        )
                    # Case 2: it could have synonyms via a P642 in P31
                    # Note: as this is a taxon, we're dealing with synonyms, not vernaculars,
                    # so the variable name is a bit misleading
                    if vernaculars_matches:
                        potential_extra_json_items.append(("instance_of_synonym", vernaculars_matches, json_item))
                    continue

            if is_taxon:
                trim_and_write_json_item(json_item, filtered_wiki_f)

                included_qids.add(Qid(json_item))

                preserved_lines += 1
            else:
                # If it's vernacular, we'll potentially write it out at the end, so save it
                potential_extra_json_items.append(("vernacular", vernaculars_matches, json_item))

        logging.info(
            "Writing extra lines at the end of the file " f"(subset of {len(potential_extra_json_items)} lines)"
        )

        for desc, linked_qids, json_item in potential_extra_json_items:
            for qid in linked_qids:
                # Only write it if it maps to one of the entries we included above
                if qid in included_qids:
                    trim_and_write_json_item(json_item, filtered_wiki_f)
                    logging.info(
                        f"Including {desc} entry: Q{Qid(json_item)} "
                        f"('{label(json_item)}','{get_wikipedia_name(json_item)}' => Q{qid}"
                    )
                    break

        filtered_wiki_f.write("]\n")


def read_wikidata_dump(wikidata_dump_file, context):
    context.wikidata_ids = set()

    for _, line in enumerate_lines_from_file(wikidata_dump_file):
        if not line.startswith('{"type":'):
            continue

        json_item = json.loads(line.rstrip().rstrip(","))
        context.wikidata_ids.add(get_wikipedia_name(json_item))


def generate_filtered_wikipedia_sql_dump(wikipedia_sql_dump_file, filtered_wikipedia_sql_dump_file, context):
    # the column numbers for each datum are specified in the SQL file, and hardcoded here.
    page_table_namespace_column = 2
    page_table_title_column = 3
    page_is_redirect_column = 4
    page_table_pagelen_column = 10

    with open_file_based_on_extension(filtered_wikipedia_sql_dump_file, "wt") as filtered_sql_f:
        current_output_line_entry_count = 0
        max_entries_per_line = 10
        with open_file_based_on_extension(wikipedia_sql_dump_file, "rt") as sql_f:
            pagelen_file = csv.reader(sql_f, quotechar="'", escapechar="\\", doublequote=False)
            match_line = "INSERT INTO `page` VALUES "
            for fields in filter(
                lambda x: False if len(x) == 0 else x[0].startswith(match_line),
                pagelen_file,
            ):
                field_num = 0
                # the records are all on the same line, separated by '),(',
                # so we need to count fields into the line.
                for field in fields:
                    try:
                        if field and field.lstrip()[0] == "(":
                            field_num = 0
                            namespace = None
                            title = None
                            is_redirect = "0"
                    except IndexError:
                        pass
                    field_num += 1
                    if field_num == page_table_namespace_column:
                        namespace = field
                    if field_num == page_table_title_column:
                        title = field
                    if field_num == page_is_redirect_column:
                        is_redirect = field
                    elif field_num == page_table_pagelen_column and namespace == "0":
                        # Only include it if it's one of our wikidata ids
                        if title in context.wikidata_ids:
                            if current_output_line_entry_count == 0:
                                filtered_sql_f.write(match_line)
                            else:
                                filtered_sql_f.write(",")

                            # Escape the quotes in the title
                            title = title.replace("'", "\\'")

                            # We leave all the other fields empty, as we don't need them
                            # e.g. (,0,'Pan_paniscus',0,,,,,,87,,)
                            filtered_sql_f.write(f"(,{namespace},'{title}',{is_redirect},,,,,,{field},,)")

                            current_output_line_entry_count += 1
                            if current_output_line_entry_count == max_entries_per_line:
                                filtered_sql_f.write(";\n")
                                current_output_line_entry_count = 0


# If it's quoted, remove the quotes and unescape it
def unquote_if_quoted(s):
    if s.startswith("'") and s.endswith("'") or s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
        return bytes(s, "utf-8").decode("unicode_escape")
    return s


def generate_filtered_pageviews_file(pageviews_file, filtered_pageviews_file, context):
    match_project = context.wikilang + ".wikipedia "

    pageviews = defaultdict(int)
    simplified_line_format = False

    for i, line in enumerate_lines_from_file(pageviews_file):
        # Check if it's the simplified format based on the first line.
        # - Simplified format:
        #   - Looks like: Chimpanzee 78033
        #   - We process all lines
        #   - Only one line for a given taxon
        # - Full format (original format from wikipedia):
        #   - Looks like: en.wikipedia Chimpanzee 7844 mobile-web 50018 A1581B168[etc...]
        #   - We ignore lines that don't start with en.wikipedia
        #   - There can be multiple lines for a given taxon (e.g. mobile vs desktop views)
        if i == 0:
            simplified_line_format = line.count(" ") == 1

        if i > 0 and i % 10000000 == 0:
            logging.info(f"Processed {i} lines")

        if not simplified_line_format and not line.startswith(match_project):
            continue

        info = line.split(" ")
        if simplified_line_format:
            title = info[0]
            views = info[1]
        else:
            title = unquote_if_quoted(info[1])
            views = info[4]

        # Only include it if it's one of our wikidata ids
        if title in context.wikidata_ids:
            pageviews[title] += int(views)

    # Write out the filtered pageviews in the simplified format
    with open_file_based_on_extension(filtered_pageviews_file, "wt") as filtered_f:
        for title, views in pageviews.items():
            filtered_f.write(title + " " + str(views) + "\n")


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
        filtered_newick_file = generate_and_cache_filtered_file(newick_file, context, generate_filtered_newick)
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

    generate_and_cache_filtered_file(eol_id_file, context, generate_filtered_eol_id_file)

    filtered_wikidata_dump_file = generate_and_cache_filtered_file(
        wikidata_dump_file, context, generate_filtered_wikidata_dump
    )

    read_wikidata_dump(filtered_wikidata_dump_file, context)

    generate_and_cache_filtered_file(wikipedia_sql_dump_file, context, generate_filtered_wikipedia_sql_dump)

    for wikipedia_pageviews_file in wikipedia_pageviews_files:
        generate_and_cache_filtered_file(wikipedia_pageviews_file, context, generate_filtered_pageviews_file)


def process_args(args):
    # Create a context object to hold various things we need to pass around
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
        "EOLidentifiers",
        help=("The gzipped EOL identifiers file, from " "https://opendata.eol.org/dataset/identifiers-csv-gz"),
    )
    parser.add_argument(
        "wikidataDumpFile",
        nargs="?",
        help=(
            "The b2zipped >4GB wikidata JSON dump, "
            "from https://dumps.wikimedia.org/wikidatawiki/entities/ (latest-all.json.bz2) "
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
        help="If true, forces the regeneration of all files, ignoring caching.",
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
