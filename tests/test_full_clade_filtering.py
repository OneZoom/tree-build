import io
import types
import os

from oz_tree_build.utilities import generate_filtered_files
from oz_tree_build.utilities.file_utils import check_identical_files
from .felidae_helpers import get_felidae_test_folders


def test_full_clade_filtering():
    """
    This is more of a functional test than a unit test. It runs the full filtering
    logic on a small clade. It then compares the output to the expected output.
    """

    args = types.SimpleNamespace()

    (
        input_path,
        expected_output_path,
        args.output_location,
    ) = get_felidae_test_folders("filtering")

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
        if f.startswith("Felidae_pageviews")
    ]
    # Sort the list of pagecount files so that the order is consistent
    args.wikipedia_totals_bz2_pageviews.sort()

    args.clade = "Leopardus"
    args.force = True
    args.compress = False

    generate_filtered_files.process_args(args)

    # Move all the generated files to the output folder, since they're generated in place
    for name in os.listdir(input_path):
        if name.startswith(args.clade):
            os.rename(
                os.path.join(input_path, name),
                os.path.join(args.output_location, name),
            )

    # Check that the output files are the same as the expected files
    check_identical_files(args.output_location, expected_output_path)
