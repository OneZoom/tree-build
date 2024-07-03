import os
import types

from oz_tree_build.taxon_mapping_and_popularity import CSV_base_table_creator
from oz_tree_build.utilities.file_utils import check_identical_files

from .felidae_helpers import get_felidae_test_folders


def test_full_felidae_generation():
    """
    This is more of a functional test than a unit test. It runs the full pipeline
    on a small clade. It then compares the output to the expected output.
    """

    args = types.SimpleNamespace()

    (
        input_path,
        expected_output_path,
        args.output_location,
    ) = get_felidae_test_folders("generation")

    # Set all the arguments, to mimic the command line
    args.Tree = os.path.join(input_path, "Felidae_AllLife_full_tree.phy")
    args.OpenTreeTaxonomy = os.path.join(input_path, "Felidae_taxonomy.tsv")
    args.EOLidentifiers = os.path.join(input_path, "Felidae_provider_ids.csv")
    args.wikidataDumpFile = os.path.join(input_path, "Felidae_latest-all.json")
    args.wikipediaSQLDumpFile = os.path.join(input_path, "Felidae_enwiki-latest-page.sql")
    args.wikipedia_totals_bz2_pageviews = [
        os.path.join(input_path, f) for f in os.listdir(input_path) if f.startswith("Felidae_pageviews")
    ]

    # Sort the list of pagecount files so that the order is consistent
    args.wikipedia_totals_bz2_pageviews.sort()

    args.verbosity = 0
    args.version = 0
    args.wikilang = "en"
    args.popularity_file = ""
    args.extra_source_file = None
    args.exclude = []
    args.info_on_focal_labels = []

    CSV_base_table_creator.process_all(args)

    # Check that the output files are the same as the expected files
    check_identical_files(args.output_location, expected_output_path)
