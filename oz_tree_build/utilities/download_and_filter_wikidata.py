"""Download the Wikidata JSON dump and filter to taxon/vernacular items.

Streams the dump directly from Wikimedia, decompresses on the fly, and
writes only the filtered results to disk.  Avoids storing the full ~90 GB
dump locally.
"""

import argparse
import logging
import os
import sys
import tempfile

from .file_utils import stream_bz2_lines_from_url
from .filter_wikidata import filter_wikidata

WIKIDATA_DUMP_URL = (
    "https://dumps.wikimedia.org/wikidatawiki/entities/latest-all.json.bz2"
)
WGET_READ_TIMEOUT = 600


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
        default=WIKIDATA_DUMP_URL,
        help="URL of the Wikidata JSON dump (.bz2)",
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


if __name__ == "__main__":
    main()
