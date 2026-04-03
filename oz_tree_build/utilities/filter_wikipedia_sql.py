"""Filter the enwiki SQL page dump to keep only pages matching wikidata titles."""

import argparse
import csv
import logging
import re
import sys
import urllib.parse
import urllib.request

from .file_utils import open_file_based_on_extension
from .filter_wikidata import load_titles_file

ENWIKI_DUMPS_URL = "https://dumps.wikimedia.org/enwiki/"

logger = logging.getLogger(__name__)


def filter_wikipedia_sql(sql_file, output_file, wikidata_titles):
    """
    Filter the enwiki page SQL dump, keeping only rows whose title appears
    in the wikidata_titles set.
    """
    page_table_namespace_column = 2
    page_table_title_column = 3
    page_is_redirect_column = 4
    page_table_pagelen_column = 10

    with open_file_based_on_extension(output_file, "wt") as filtered_sql_f:
        current_output_line_entry_count = 0
        max_entries_per_line = 10
        with open_file_based_on_extension(sql_file, "rt") as sql_f:
            pagelen_file = csv.reader(sql_f, quotechar="'", escapechar="\\", doublequote=False)
            match_line = "INSERT INTO `page` VALUES "
            for fields in filter(
                lambda x: False if len(x) == 0 else x[0].startswith(match_line),
                pagelen_file,
            ):
                field_num = 0
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
                        if title in wikidata_titles:
                            if current_output_line_entry_count == 0:
                                filtered_sql_f.write(match_line)
                            else:
                                filtered_sql_f.write(",")

                            title = title.replace("'", "\\'")
                            filtered_sql_f.write(f"(,{namespace},'{title}',{is_redirect},,,,,,{field},,)")

                            current_output_line_entry_count += 1
                            if current_output_line_entry_count == max_entries_per_line:
                                filtered_sql_f.write(";\n")
                                current_output_line_entry_count = 0


def main():
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sql_file", help="The enwiki SQL page dump file (optionally gzipped)")
    parser.add_argument("titles_file", help="wikidata_titles.txt file (one title per line)")
    parser.add_argument("-o", "--output", required=True, help="Output path for filtered SQL file")
    args = parser.parse_args()

    wikidata_titles = load_titles_file(args.titles_file)
    logging.info(f"Loaded {len(wikidata_titles)} wikidata titles")
    filter_wikipedia_sql(args.sql_file, args.output, wikidata_titles)


def discover_latest_enwiki_sql_url(
    base_url=ENWIKI_DUMPS_URL, timeout=30
):
    """Find the URL of the most recent enwiki-YYYYMMDD-page.sql.gz dump.

    Fetches the directory listing at *base_url*, collects the dated
    sub-folders (``YYYYMMDD/``), and walks them in reverse-chronological
    order until it finds one whose dump status page contains a link to
    the ``page.sql.gz`` file.

    Returns the full URL to that file.
    Raises ``RuntimeError`` if no suitable dump can be found.
    """
    folder_re = re.compile(r'href="(\d{8})/"')
    file_re_template = r'href="([^"]*enwiki-{date}-page\.sql\.gz)"'

    index_html = urllib.request.urlopen(
        base_url, timeout=timeout
    ).read().decode()

    dates = sorted(folder_re.findall(index_html), reverse=True)
    if not dates:
        raise RuntimeError(f"No dated folders found at {base_url}")

    for date in dates:
        folder_url = f"{base_url}{date}/"
        logger.info("Checking %s", folder_url)
        try:
            folder_html = urllib.request.urlopen(
                folder_url, timeout=timeout
            ).read().decode()
        except urllib.error.URLError as exc:
            logger.warning("Could not fetch %s: %s", folder_url, exc)
            continue

        match = re.search(
            file_re_template.format(date=date), folder_html
        )
        if match:
            url = urllib.parse.urljoin(folder_url, match.group(1))
            logger.info("Found latest enwiki SQL dump: %s", url)
            return url

    raise RuntimeError(
        f"No enwiki-YYYYMMDD-page.sql.gz file found in any folder at {base_url}"
    )


def discover_main():
    """CLI entry point: discover the latest enwiki SQL dump URL."""
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    url = discover_latest_enwiki_sql_url()
    print(url)


if __name__ == "__main__":
    main()
