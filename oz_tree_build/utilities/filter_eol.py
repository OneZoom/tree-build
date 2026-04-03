"""Filter EOL provider IDs CSV to keep only relevant sources."""

import argparse
import logging
import sys

from ..taxon_mapping_and_popularity.CSV_base_table_creator import iucn_num
from .file_utils import open_file_based_on_extension
from .filter_common import read_taxonomy_source_ids


def filter_eol_ids(eol_id_file, output_file, source_ids, clade=None):
    """
    Filter the EOL identifiers file, keeping only rows from known providers
    whose IDs appear in the taxonomy. In non-clade (full-tree) mode, all rows
    from known providers are kept.

    Returns nothing; writes filtered output to output_file.
    """
    eol_sources = {"676": "ncbi", "459": "worms", "767": "gbif", str(iucn_num): "iucn"}
    iucn_lines = []
    known_names = set()

    with open_file_based_on_extension(eol_id_file, "rt") as eol_f:
        with open_file_based_on_extension(output_file, "wt") as filtered_eol_f:
            for i, line in enumerate(eol_f):
                if i == 0:
                    filtered_eol_f.write(line)
                    continue

                fields = line.split(",")

                if fields[2] not in eol_sources:
                    continue

                try:
                    eol_id = int(fields[1])
                except ValueError:
                    continue

                if not clade:
                    filtered_eol_f.write(line)
                    continue

                if fields[2] == str(iucn_num):
                    iucn_lines.append(line)
                elif eol_id in source_ids[eol_sources[fields[2]]]:
                    filtered_eol_f.write(line)
                    known_names.add(fields[4])

            for line in iucn_lines:
                fields = line.split(",")
                if fields[4] in known_names:
                    filtered_eol_f.write(line)

    logging.info(
        f"Found {len(source_ids['ncbi'])} NCBI ids, "
        f"{len(source_ids['if'])} IF ids, "
        f"{len(source_ids['worms'])} WoRMS ids, "
        f"{len(source_ids['irmng'])} IRMNG ids, "
        f"{len(source_ids['gbif'])} GBIF ids"
    )


def main():
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eol_file", help="The EOL identifiers CSV file (optionally gzipped)")
    parser.add_argument("taxonomy_file", help="The OpenTree taxonomy.tsv file")
    parser.add_argument("-o", "--output", required=True, help="Output path for filtered EOL CSV")
    args = parser.parse_args()

    source_ids = read_taxonomy_source_ids(args.taxonomy_file)
    filter_eol_ids(args.eol_file, args.output, source_ids)


if __name__ == "__main__":
    main()
