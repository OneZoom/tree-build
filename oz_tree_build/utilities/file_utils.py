"""
Miscellaneous file utilities
"""

import bz2
import codecs
import gzip
import os
import shutil
import subprocess

__author__ = "David Ebbo"


def open_file_based_on_extension(filename, mode):
    # Open a file, whether it's uncompressed, bz2 or gz
    if filename.endswith(".bz2"):
        return bz2.open(filename, mode, encoding="utf-8")
    elif filename.endswith(".gz"):
        return gzip.open(filename, mode, encoding="utf-8")
    else:
        return open(filename, mode, encoding="utf-8")


def stream_bz2_lines_from_url(url, read_timeout=120):
    """
    Stream a .bz2 file over HTTP via wget and yield decompressed lines.
    wget handles timeouts, connection management, and progress display;
    Python handles decompression and line splitting.
    """
    if not shutil.which("wget"):
        raise RuntimeError("wget is required but not found on PATH")

    wget = subprocess.Popen(
        [
            "wget", "-q", "--show-progress", "-O", "-",
            "--connect-timeout=30",
            f"--read-timeout={read_timeout}",
            "--header=User-Agent: OneZoom-tree-build/1.0",
            url,
        ],
        stdout=subprocess.PIPE,
        stderr=None,
    )

    decompressor = bz2.BZ2Decompressor()
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    line_buf = ""

    try:
        while True:
            chunk = wget.stdout.read(1024 * 1024)
            if not chunk:
                break
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
        if rc != 0:
            raise RuntimeError(f"wget failed (exit {rc})")


def enumerate_lines_from_file(filename):
    """Enumerate the lines in a file, whether it's uncompressed, bz2 or gz."""
    with open_file_based_on_extension(filename, "rt") as f:
        for line_num, line in enumerate(iter(f.readline, "")):
            yield line_num, line


def check_identical_files(output_location, expected_output_path):
    """
    Checks that the output files are the same as the expected files
    """
    for name in os.listdir(expected_output_path):
        if name.startswith("."):
            continue

        expected_file_path = os.path.join(expected_output_path, name)
        output_file_path = os.path.join(output_location, name)

        assert list(open(expected_file_path)) == list(
            open(output_file_path)
        ), f"File {name} is not the same as the expected output file"
