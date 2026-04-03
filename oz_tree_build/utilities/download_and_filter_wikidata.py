"""Download the Wikidata JSON dump and filter to taxon/vernacular items.

Streams the dump directly from Wikimedia, decompresses on the fly, and
writes only the filtered results to disk.  Avoids storing the full ~90 GB
dump locally.
"""

import argparse
import logging
import os
import re
import sys
import tempfile
import urllib.request

from .file_utils import stream_bz2_lines_from_url
from .filter_wikidata import filter_wikidata

WIKIDATA_ENTITIES_URL = "https://dumps.wikimedia.org/wikidatawiki/entities/"
WGET_READ_TIMEOUT = 600

logger = logging.getLogger(__name__)


def discover_latest_wikidata_dump_url(
    base_url=WIKIDATA_ENTITIES_URL, timeout=30
):
    """Find the URL of the most recent dated wikidata-YYYYMMDD-all.json.bz2 dump.
    We don't use the symlinked latest-all.json.bz2 file because we want to know the date."""
    folder_re = re.compile(r'href="(\d{8})/"')
    file_re_template = r'href="(wikidata-{date}-all\.json\.bz2)"'

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
            url = f"{folder_url}{match.group(1)}"
            logger.info("Found latest dump: %s", url)
            return url

    raise RuntimeError(
        f"No wikidata-YYYYMMDD-all.json.bz2 file found in any folder at {base_url}"
    )


def stream_and_filter(url, output_path, wikilang="en", dont_trim_sitelinks=False):
    """
    Stream a remote Wikidata .bz2 dump, filter it, and write the result.
    Uses a temp file + rename for atomicity.
    """
    lines = stream_bz2_lines_from_url(url, read_timeout=WGET_READ_TIMEOUT)

    dir_name = os.path.dirname(output_path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    os.close(fd)
    try:
        filter_wikidata(
            lines,
            tmp_path,
            wikilang=wikilang,
            dont_trim_sitelinks=dont_trim_sitelinks,
        )
        os.replace(tmp_path, output_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def main():
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output path for filtered wikidata JSON",
    )
    parser.add_argument("--wikilang", default="en", help="Wikipedia language code")
    parser.add_argument(
        "--url",
        required=True,
    )
    parser.add_argument(
        "--dont-trim-sitelinks",
        action="store_true",
        default=False,
        help="Keep the full sitelinks value for all languages",
    )
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    logging.info(f"Streaming Wikidata dump from {args.url}")
    stream_and_filter(
        args.url,
        args.output,
        wikilang=args.wikilang,
        dont_trim_sitelinks=args.dont_trim_sitelinks,
    )
    logging.info(f"Done: {args.output}")


def discover_main():
    """CLI entry point: discover the latest wikidata dump URL."""
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    url = discover_latest_wikidata_dump_url()
    print(url)

if __name__ == "__main__":
    main()
