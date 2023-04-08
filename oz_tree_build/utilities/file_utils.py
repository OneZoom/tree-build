"""
Miscellaneous file utilities
"""

import bz2
import gzip

__author__ = "David Ebbo"


def open_file_based_on_extension(filename, mode):
    # Open a file, whether it's uncompressed, bz2 or gz
    if filename.endswith(".bz2"):
        return bz2.open(filename, mode, encoding="utf-8")
    elif filename.endswith(".gz"):
        return gzip.open(filename, mode, encoding="utf-8")
    else:
        return open(filename, mode, encoding="utf-8")


def enumerate_lines_from_file(filename):
    # Enumerate the lines in a file, whether it's uncompressed, bz2 or gz
    with open_file_based_on_extension(filename, "rt") as f:
        for line_num, line in enumerate(f):
            yield line_num, line
