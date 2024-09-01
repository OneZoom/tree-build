"""
Miscellaneous file utilities
"""

import bz2
import gzip
import os
import time

__author__ = "David Ebbo"


def open_file_based_on_extension(filename, mode):
    # Open a file, whether it's uncompressed, bz2 or gz
    if filename.endswith(".bz2"):
        return bz2.open(filename, mode, encoding="utf-8")
    elif filename.endswith(".gz"):
        return gzip.open(filename, mode, encoding="utf-8")
    else:
        return open(filename, mode, encoding="utf-8")


def enumerate_lines_from_file(filename, print_every=None, print_line_num_func=None):
    """
    Enumerate the lines in a file, whether it's uncompressed, bz2 or gz. If print_every
    is given as an integer, print a message out every print_every lines. If
    print_line_num_func is given, it should be a function that takes in the line number
    and returns the string to print out.
    """
    underlying_file_size = os.path.getsize(filename)
    start_time = time.time()
    with open_file_based_on_extension(filename, "rt") as f:
        if print_every is not None:
            try:
                underlying_file = f.buffer.fileobj  # gzip
            except AttributeError:
                try:
                    underlying_file = f.buffer._buffer.raw._fp  # b2zip
                except AttributeError:
                    underlying_file = f  # plain
        for line_num, line in enumerate(iter(f.readline, "")):
            if print_every is not None and line_num != 0 and line_num % print_every == 0:
                underlying_file_pos = underlying_file.tell()
                percent_done = 100 * underlying_file_pos / underlying_file_size
                elapsed_time = time.time() - start_time
                time_left = elapsed_time * (100 - percent_done) / percent_done
                expected_ETA = time.strftime("%H:%M:%S", time.localtime(time.time() + time_left))
                if print_line_num_func is not None:
                    line_num_str = print_line_num_func(line_num)
                else:
                    line_num_str = f"Processing line {line_num}"
                print(f"{percent_done:.2f}% read. " + line_num_str + f" ETA: {expected_ETA}")
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
