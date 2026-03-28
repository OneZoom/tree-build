"""Filter the massive wikidata JSON dump to taxon and vernacular items."""

import argparse
import json
import logging
import sys

from .._OZglobals import wikiflags
from ..taxon_mapping_and_popularity.OTT_popularity_mapping import (
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

WIKIDATA_MASK = {
    "type": KEEP,
    "id": KEEP,
    "labels": {"en": {"value": KEEP}},
    "claims": {
        "P31": [
            {
                "mainsnak": {"datavalue": {"value": {"numeric-id": KEEP}}},
                "qualifiers": {
                    "P642": [{"datavalue": {"value": {"numeric-id": KEEP}}}]
                },
            }
        ],
        "P685": [{"mainsnak": {"datavalue": {"value": KEEP}}}],
        "P846": [{"mainsnak": {"datavalue": {"value": KEEP}}}],
        "P850": [{"mainsnak": {"datavalue": {"value": KEEP}}}],
        "P1391": [{"mainsnak": {"datavalue": {"value": KEEP}}}],
        "P5055": [{"mainsnak": {"datavalue": {"value": KEEP}}}],
        "P830": [{"mainsnak": {"datavalue": {"value": KEEP}}}],
        "P961": [{"mainsnak": {"datavalue": {"value": KEEP}}}],
        "P9157": [{"mainsnak": {"datavalue": {"value": KEEP}}}],
        "P3151": [{"mainsnak": {"datavalue": {"value": KEEP}}}],
        "P141": [{"references": [{"snaks": {"P627": [{"datavalue": {"value": KEEP}}]}}]}],
        "P1420": [{"mainsnak": {"datavalue": {"value": {"numeric-id": KEEP}}}}],
        "P18": [
            {
                "mainsnak": {"datavalue": {"value": KEEP}},
                "rank": KEEP,
            }
        ],
        "P1843": [
            {
                "mainsnak": {"datavalue": {"value": KEEP}},
                "rank": KEEP,
            }
        ],
    },
    "sitelinks": {ANY: {"title": KEEP}},
}


def filter_wikidata(
    lines,
    output_file,
    source_ids=None,
    clade=None,
    wikilang="en",
    dont_trim_sitelinks=False,
):
    """
    Filter the wikidata JSON dump, keeping only taxon and vernacular items,
    and trimming each item to only the fields we consume.

    *lines* should be an iterable of raw dump lines (e.g. from
    ``stream_bz2_lines_from_url`` or ``enumerate_lines_from_file``).
    """
    sitelinks_key = f"{wikilang}wiki"

    def trim_and_write_json_item(json_item, filtered_wiki_f):
        apply_mask_to_object_graph(json_item, WIKIDATA_MASK)

        if dont_trim_sitelinks:
            json_item["sitelinks"] = {
                k: v for k, v in json_item["sitelinks"].items() if k.endswith("wiki")
            }
        else:
            json_item["sitelinks"] = {
                k: v if k == sitelinks_key else {}
                for k, v in json_item["sitelinks"].items()
                if k.endswith("wiki") and len(k) == 6 and k[:2] in wikiflags
            }

        filtered_wiki_f.write(json.dumps(json_item, separators=(",", ":")))
        filtered_wiki_f.write(",\n")

    included_qids = set()
    potential_extra_json_items = []

    with open_file_based_on_extension(output_file, "wt") as filtered_wiki_f:
        filtered_wiki_f.write("[\n")
        preserved_lines = 0

        for line_num, line in enumerate(lines):
            if line_num > 0 and line_num % 100_000 == 0:
                logging.info(
                    f"Processed {line_num} lines, kept {preserved_lines}"
                )

            if not (line.startswith('{"type":') and quick_byte_match.search(line)):
                continue

            json_item = json.loads(line.rstrip().rstrip(","))

            try:
                is_taxon, vernaculars_matches = find_taxon_and_vernaculars(json_item)
            except KeyError:
                continue

            if not is_taxon and not len(vernaculars_matches) > 0:
                continue

            if clade and is_taxon and source_ids:
                if not len(JSON_contains_known_dbID(json_item, source_ids)) > 0:
                    if "P1420" in json_item["claims"] and json_item["sitelinks"]:
                        potential_extra_json_items.append(
                            (
                                "taxon_synonym",
                                {wikidata_value(i["mainsnak"])["numeric-id"] for i in json_item["claims"]["P1420"]},
                                json_item,
                            )
                        )
                    if vernaculars_matches:
                        potential_extra_json_items.append(("instance_of_synonym", vernaculars_matches, json_item))
                    continue

            if is_taxon:
                trim_and_write_json_item(json_item, filtered_wiki_f)
                included_qids.add(Qid(json_item))
                preserved_lines += 1
            else:
                potential_extra_json_items.append(("vernacular", vernaculars_matches, json_item))

        logging.info(
            "Writing extra lines at the end of the file "
            f"(subset of {len(potential_extra_json_items)} lines)"
        )

        for desc, linked_qids, json_item in potential_extra_json_items:
            for qid in linked_qids:
                if qid in included_qids:
                    trim_and_write_json_item(json_item, filtered_wiki_f)
                    logging.info(
                        f"Including {desc} entry: Q{Qid(json_item)} "
                        f"('{label(json_item)}','{get_wikipedia_name(json_item)}' => Q{qid}"
                    )
                    break

        filtered_wiki_f.write("]\n")


def extract_wikidata_titles(filtered_wikidata_file):
    """
    Read a filtered wikidata JSON file and return the set of Wikipedia page
    titles (used by downstream SQL and pageview filters).
    """
    titles = set()
    for _, line in enumerate_lines_from_file(filtered_wikidata_file):
        if not line.startswith('{"type":'):
            continue
        json_item = json.loads(line.rstrip().rstrip(","))
        title = get_wikipedia_name(json_item)
        if title is not None:
            titles.add(title)
    return titles


def write_titles_file(titles, output_path):
    """Write the set of titles to a text file, one per line."""
    with open(output_path, "w") as f:
        for title in sorted(titles):
            f.write(title + "\n")


def load_titles_file(titles_path):
    """Load a titles text file into a set."""
    with open(titles_path) as f:
        return {line.strip() for line in f if line.strip()}


def main():
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wikidata_file", help="The wikidata JSON dump file (bz2 or plain)")
    parser.add_argument("-o", "--output", required=True, help="Output path for filtered wikidata JSON")
    parser.add_argument("--wikilang", default="en", help="Wikipedia language code")
    parser.add_argument(
        "--dont-trim-sitelinks",
        action="store_true",
        default=False,
        help="Keep the full sitelinks value for all languages",
    )
    args = parser.parse_args()

    lines = (line for _, line in enumerate_lines_from_file(args.wikidata_file))
    filter_wikidata(
        lines,
        args.output,
        wikilang=args.wikilang,
        dont_trim_sitelinks=args.dont_trim_sitelinks,
    )


def extract_titles_main():
    """Extract Wikipedia page titles from a filtered wikidata JSON file."""
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)

    parser = argparse.ArgumentParser(description=extract_titles_main.__doc__)
    parser.add_argument("filtered_wikidata_file", help="The filtered wikidata JSON file")
    parser.add_argument("-o", "--output", required=True, help="Output path for wikidata_titles.txt")
    args = parser.parse_args()

    titles = extract_wikidata_titles(args.filtered_wikidata_file)
    write_titles_file(titles, args.output)
    logging.info(f"Wrote {len(titles)} titles to {args.output}")


if __name__ == "__main__":
    main()
