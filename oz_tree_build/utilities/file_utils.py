"""
Miscellaneous file utilities
"""

import bz2
import gzip
import io
import os

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


def check_identical_files(output_location, expected_output_path):
    """
    Checks that the output files are the same as the expected files
    """
    for name in os.listdir(expected_output_path):
        if name.startswith("."):
            continue

        expected_file_path = os.path.join(expected_output_path, name)
        output_file_path = os.path.join(output_location, name)

        assert list(io.open(expected_file_path)) == list(
            io.open(output_file_path)
        ), f"File {name} is not the same as the expected output file"
