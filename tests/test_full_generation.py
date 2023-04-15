import io
import types
import os

from oz_tree_build.taxon_mapping_and_popularity import CSV_base_table_creator


def test_full_felidae_generation():
    """
    This is more of a functional test than a unit test. It runs the full pipeline
    on a small a small clade. It then compares the output to the expected output.
    """

    args = types.SimpleNamespace()

    test_code_path = os.path.dirname(os.path.realpath(__file__))
    test_files_path = os.path.join(test_code_path, "test_files_felidae")
    input_path = os.path.join(test_files_path, "input_files")
    expected_output_path = os.path.join(test_files_path, "expected_output_files")
    args.output_location = os.path.join(test_files_path, "output_files")

    # Remove the output files if they already exist
    for name in os.listdir(args.output_location):
        if name.startswith("."):
            continue

        os.remove(os.path.join(args.output_location, name))

    # Set all the arguments, to mimic the command line
    args.Tree = os.path.join(input_path, "Felidae_AllLife_full_tree.phy")
    args.OpenTreeTaxonomy = os.path.join(input_path, "Felidae_taxonomy.tsv")
    args.EOLidentifiers = os.path.join(input_path, "Felidae_provider_ids.csv")
    args.wikidataDumpFile = os.path.join(input_path, "Felidae_latest-all.json")
    args.wikipediaSQLDumpFile = os.path.join(
        input_path, "Felidae_enwiki-latest-page.sql"
    )
    args.wikipedia_totals_bz2_pageviews = [
        os.path.join(input_path, f)
        for f in os.listdir(input_path)
        if f.startswith("Felidae_pagecounts")
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
    for name in os.listdir(expected_output_path):
        if name.startswith("."):
            continue

        expected_file_path = os.path.join(expected_output_path, name)
        output_file_path = os.path.join(args.output_location, name)

        assert list(io.open(expected_file_path)) == list(
            io.open(output_file_path)
        ), f"File {name} is not the same as the expected output file"
