"""Filter Wikipedia pageview files to keep only pages matching wikidata titles."""

import argparse
import logging
import os
import sys
from collections import defaultdict

from .file_utils import enumerate_lines_from_file, open_file_based_on_extension
from .filter_wikidata import load_titles_file


def unquote_if_quoted(s):
    if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
        s = s[1:-1]
        return bytes(s, "utf-8").decode("unicode_escape")
    return s


def filter_pageview_lines(lines, wikidata_titles, wikilang="en"):
    """
    Filter an iterable of pageview lines, keeping only entries whose title
    appears in the wikidata_titles set. Returns a dict mapping title to
    aggregated view count.
    """
    match_project = wikilang + ".wikipedia "
    pageviews = defaultdict(int)
    simplified_line_format = False

    for i, line in enumerate(lines):
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

        if title in wikidata_titles:
            pageviews[title] += int(views)

    return pageviews


def write_filtered_pageviews(pageviews, output_file):
    """Write aggregated pageview counts to file in ``Title viewcount`` format."""
    with open_file_based_on_extension(output_file, "wt") as filtered_f:
        for title, views in pageviews.items():
            filtered_f.write(title + " " + str(views) + "\n")


def filter_pageviews(pageviews_file, output_file, wikidata_titles, wikilang="en"):
    """
    Filter a single pageview file, keeping only entries whose title appears
    in the wikidata_titles set. Aggregates views per title and writes output
    in the simplified format (``Title viewcount``).
    """
    lines = (line for _, line in enumerate_lines_from_file(pageviews_file))
    pageviews = filter_pageview_lines(lines, wikidata_titles, wikilang)
    write_filtered_pageviews(pageviews, output_file)


def main():
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pageview_files", nargs="+", help="One or more pageview files (optionally bz2-compressed)")
    parser.add_argument("--titles-file", required=True, help="wikidata_titles.txt file (one title per line)")
    parser.add_argument("-o", "--output-dir", required=True, help="Output directory for filtered pageview files")
    parser.add_argument("--wikilang", default="en", help="Wikipedia language code")
    args = parser.parse_args()

    wikidata_titles = load_titles_file(args.titles_file)
    logging.info(f"Loaded {len(wikidata_titles)} wikidata titles")

    os.makedirs(args.output_dir, exist_ok=True)

    for pv_file in args.pageview_files:
        basename = os.path.basename(pv_file)
        if basename.endswith(".bz2"):
            basename = basename[:-4]
        output_file = os.path.join(args.output_dir, f"OneZoom_{basename}")
        logging.info(f"Filtering {pv_file} -> {output_file}")
        filter_pageviews(pv_file, output_file, wikidata_titles, wikilang=args.wikilang)


if __name__ == "__main__":
    main()
