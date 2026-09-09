"""
Add version number / gzip output files as a final stage of the pipeline

In addition to versioning data files, the SQL import script is also modified.
CSV filenames have their version added, and as a final step the version number
is inserted into the DB as the parent of the root.
"""

import argparse
import logging
import os
import re
import shutil
import subprocess

from ..utilities.debug_util import parse_args_and_add_logging_switch

logger = logging.getLogger(__name__)


def process(in_files, out_dir, version_number):
    """
    Copy list of ``in_files`` to ``out_dir``, with ``version_number`` appended to name
    """

    def add_version(f_name):
        return re.sub(
            # Extract any existing version number / extension from filename
            r"(_\d+)?(\.[a-zA-Z]+)$",
            # Replace with verison number / extension
            "_" + str(version_number) + r"\2",
            f_name,
        )

    for input_path in in_files:
        input_name = os.path.basename(input_path)
        output_path = os.path.join(out_dir, add_version(input_name))

        logger.info(f"{input_path} -> {output_path}")
        if input_name == "import.sql":
            with open(input_path) as in_f, open(output_path, "w") as out_f:
                for l in in_f:
                    # Replace any instance of an input filename with it's versioned equivalent
                    for repl_path in in_files:
                        repl_name = os.path.basename(repl_path)
                        l = l.replace("'" + repl_name + "'", "'" + add_version(repl_name) + "'")
                    out_f.write(l)
                    # Extra command to bodge version number into root's parent
                out_f.writelines(f"UPDATE ordered_nodes SET parent = -{version_number} WHERE id = 1;\n")
        else:
            shutil.copyfile(input_path, output_path)
        subprocess.call(["gzip", "-9fk", output_path])
        logger.info("Done")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--outdir",
        "-o",
        default=os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "OZtree",
            "static",
            "FinalOutputs",
            "data",
        ),
        help="output filepath of cut_position_map",
    )
    parser.add_argument(
        "in_files",
        nargs="+",
        metavar="FILE",
        help="Files to move to outdir, with versions appended if not present",
    )
    parser.add_argument(
        "--version",
        type=int,
        help=("Version number / serial to append to file names, if not provided use mtime of first in_file"),
    )
    parser.add_argument(
        "--out_dir",
        default="data/out",
        help=("Directory to write output files to"),
    )
    args = parse_args_and_add_logging_switch(parser)

    process(
        args.in_files,
        args.out_dir,
        int(os.path.getmtime(args.in_files[0])) if args.version is None else args.version,
    )


if __name__ == "__main__":
    main()
