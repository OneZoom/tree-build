"""Shared utilities for the filter modules."""

import csv

from .file_utils import open_file_based_on_extension


def read_taxonomy_source_ids(taxonomy_file):
    """
    Read an OpenTree taxonomy.tsv file and return a dict mapping source
    names to sets of integer IDs. Used by filter_eol and filter_wikidata
    (in clade mode).
    """
    sources = {"ncbi", "if", "worms", "irmng", "gbif"}
    source_ids = {source: set() for source in sources}

    with open_file_based_on_extension(taxonomy_file, "rt") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for OTTrow in reader:
            sourceinfo = OTTrow["sourceinfo"]
            for srcs in sourceinfo.split(","):
                src, src_id = srcs.split(":", 1)
                if src in sources:
                    try:
                        source_ids[src].add(int(src_id))
                    except ValueError:
                        pass

    return source_ids
