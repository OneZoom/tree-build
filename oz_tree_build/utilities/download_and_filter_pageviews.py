"""Download pageview files from Wikimedia and filter to wikidata titles.

Streams monthly pageview dumps directly from
https://dumps.wikimedia.org/other/pageview_complete/monthly/,
decompresses on the fly, and writes only the filtered results to disk.
Already-filtered months are skipped unless the titles file has changed.
"""

import argparse
import bz2
import codecs
import hashlib
import itertools
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

from .filter_pageviews import filter_pageview_lines, write_filtered_pageviews
from .filter_wikidata import load_titles_file

BASE_URL = "https://dumps.wikimedia.org/other/pageview_complete/monthly/"
TITLES_HASH_FILE = ".titles_hash"
WGET_READ_TIMEOUT = 120  # seconds of no data before wget gives up


def _fetch_index(url):
    """Fetch an Apache directory index page and return its HTML."""
    print(f"Fetching index from {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "OneZoom-tree-build/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def discover_pageview_months(base_url=BASE_URL):
    """
    Crawl the Wikimedia monthly pageview directory listing and yield
    (url, filename) tuples for ``*-user.bz2`` files, most recent first.

    Iterates years and months in reverse so callers needing only the N most
    recent months can stop early without fetching every index page.
    """
    year_pattern = re.compile(r'href="(\d{4}/)"')
    month_dir_pattern = re.compile(r'href="(\d{4}-\d{2}/)"')
    user_file_pattern = re.compile(r'href="(pageviews-\d{6}-user\.bz2)"')

    years_html = _fetch_index(base_url)
    year_dirs = sorted(
        (m.group(1) for m in year_pattern.finditer(years_html)), reverse=True
    )

    for year_dir in year_dirs:
        year_url = base_url + year_dir

        months_html = _fetch_index(year_url)
        month_dirs = sorted(
            (m.group(1) for m in month_dir_pattern.finditer(months_html)),
            reverse=True,
        )

        for month_dir in month_dirs:
            month_url = year_url + month_dir

            files_html = _fetch_index(month_url)
            for file_match in user_file_pattern.finditer(files_html):
                filename = file_match.group(1)
                file_url = month_url + filename
                yield file_url, filename


def _stream_bz2_lines(url):
    """
    Stream a .bz2 file over HTTP via wget and yield decompressed lines.
    wget handles timeouts and connection management; Python handles decompression.
    """
    if not shutil.which("wget"):
        raise RuntimeError("wget is required but not found on PATH")

    wget = subprocess.Popen(
        [
            "wget", "-q", "-O", "-",
            "--connect-timeout=30",
            f"--read-timeout={WGET_READ_TIMEOUT}",
            "--header=User-Agent: OneZoom-tree-build/1.0",
            url,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    decompressor = bz2.BZ2Decompressor()
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    line_buf = ""
    bytes_read = 0

    try:
        while True:
            chunk = wget.stdout.read(1024 * 1024)
            if not chunk:
                break
            bytes_read += len(chunk)
            if bytes_read % (500 * 1024 * 1024) < 1024 * 1024:
                logging.info(f"  Downloaded {bytes_read / (1024**3):.1f} GB so far...")
            try:
                raw = decompressor.decompress(chunk)
            except EOFError:
                break
            text = decoder.decode(raw)
            line_buf += text
            parts = line_buf.split("\n")
            line_buf = parts[-1]
            for line in parts[:-1]:
                yield line

        trailing = decoder.decode(b"", final=True)
        line_buf += trailing
        if line_buf:
            yield line_buf
    finally:
        wget.stdout.close()
        if wget.poll() is None:
            wget.terminate()
        rc = wget.wait()
        stderr_out = wget.stderr.read().decode("utf-8", errors="replace").strip()
        wget.stderr.close()
        if rc != 0:
            raise RuntimeError(f"wget failed (exit {rc}): {stderr_out}")


def _compute_file_hash(path):
    """Return the SHA-256 hex digest of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _output_filename(pageview_filename):
    """Map a raw pageview filename to its filtered output name."""
    basename = pageview_filename
    if basename.endswith(".bz2"):
        basename = basename[:-4]
    return f"OneZoom_{basename}"


def _check_and_update_titles_hash(output_dir, titles_file):
    """
    Compare the stored titles hash with the current file.  Returns True if
    the cache is still valid.  Clears existing output files and updates the
    hash when it changes.
    """
    current_hash = _compute_file_hash(titles_file)
    hash_path = os.path.join(output_dir, TITLES_HASH_FILE)

    if os.path.exists(hash_path):
        with open(hash_path) as f:
            stored_hash = f.read().strip()
        if stored_hash == current_hash:
            return True
        logging.info("Titles file changed -- clearing cached pageview outputs")
        for name in os.listdir(output_dir):
            if name == TITLES_HASH_FILE:
                continue
            os.remove(os.path.join(output_dir, name))

    with open(hash_path, "w") as f:
        f.write(current_hash)
    return False


def stream_and_filter(url, output_path, wikidata_titles, wikilang="en"):
    """
    Stream a remote .bz2 pageview file, filter it, and write the result.
    Uses a temp file + rename for atomicity.
    """
    lines = _stream_bz2_lines(url)
    pageviews = filter_pageview_lines(lines, wikidata_titles, wikilang)

    dir_name = os.path.dirname(output_path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    os.close(fd)
    try:
        write_filtered_pageviews(pageviews, tmp_path)
        os.replace(tmp_path, output_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def main():
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--titles-file",
        required=True,
        help="wikidata_titles.txt file (one title per line)",
    )
    parser.add_argument(
        "--months",
        type=int,
        required=True,
        help="Number of most recent months to process",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        required=True,
        help="Output directory for filtered pageview files",
    )
    parser.add_argument("--wikilang", default="en", help="Wikipedia language code")
    parser.add_argument(
        "--base-url",
        default=BASE_URL,
        help="Base URL for the Wikimedia pageview dumps",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    cache_valid = _check_and_update_titles_hash(args.output_dir, args.titles_file)
    if cache_valid:
        logging.info("Titles file unchanged -- cached outputs are valid")
    else:
        logging.info("Titles file is new or changed -- will reprocess all months")

    wikidata_titles = load_titles_file(args.titles_file)
    logging.info(f"Loaded {len(wikidata_titles)} wikidata titles")

    logging.info("Discovering available pageview months from Wikimedia...")
    selected = list(itertools.islice(
        discover_pageview_months(args.base_url), args.months
    ))
    selected.reverse()
    logging.info(
        f"Selected {len(selected)} most recent months"
    )

    for i, (url, filename) in enumerate(selected, 1):
        output_file = os.path.join(args.output_dir, _output_filename(filename))

        if os.path.exists(output_file):
            logging.info(f"[{i}/{len(selected)}] Skipping {filename} (already filtered)")
            continue

        logging.info(f"[{i}/{len(selected)}] Streaming and filtering {filename}...")
        stream_and_filter(url, output_file, wikidata_titles, wikilang=args.wikilang)
        logging.info(f"[{i}/{len(selected)}] Done: {output_file}")

    logging.info("All pageview months up to date")


if __name__ == "__main__":
    main()
